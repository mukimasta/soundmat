"""系统监测的探针：从操作系统读取音频服务、声卡、机器和网络的情况。

每个探针都可能失败（开发机上没有 JACK、不是树莓派、没装 nmcli……），失败时返回 None，
看板上显示为"未知"，而不是沿用旧值。探针只读，不改变系统状态。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
from pathlib import Path


def _run(args: list[str], timeout: float = 2.0) -> str | None:
    if shutil.which(args[0]) is None:
        return None
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout if p.returncode == 0 else None


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def _process(name: str) -> tuple[Path, list[str]] | None:
    """找一个正在运行的进程（按可执行文件名），返回它的 /proc 目录和命令行参数。"""
    proc = Path("/proc")
    if not proc.is_dir():
        return None
    for d in proc.iterdir():
        if not d.name.isdigit():
            continue
        try:
            raw = (d / "cmdline").read_bytes()
        except OSError:
            continue
        args = [a.decode(errors="replace") for a in raw.split(b"\0") if a]
        if args and os.path.basename(args[0]) == name:
            return d, args
    return None


def _process_cmdline(name: str) -> list[str] | None:
    found = _process(name)
    return None if found is None else found[1]


def _started_at(proc_dir: Path) -> float | None:
    """进程启动的 Unix 时间：开机时刻（/proc/stat 的 btime）加上进程的启动节拍数。

    不用 systemd 记的启动时间：树莓派没有电池时钟，开机时还没校时，那个时间可能差好几个小时。
    """
    try:
        ticks = int((proc_dir / "stat").read_text().rsplit(")", 1)[1].split()[19])
        btime = next(int(line.split()[1]) for line in Path("/proc/stat").read_text().splitlines()
                     if line.startswith("btime "))
        return btime + ticks / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError, StopIteration):
        return None


def sound_cards() -> list[dict] | None:
    """ALSA 声卡列表：[{index, id, name}]。"""
    text = _read("/proc/asound/cards")
    return None if text is None else parse_cards(text)


def parse_cards(text: str) -> list[dict]:
    cards = []
    for m in re.finditer(r"^\s*(\d+)\s+\[(\S+)\s*\]:\s*(.+?)\n\s+(.+)$", text + "\n", re.M):
        cards.append({"index": int(m.group(1)), "id": m.group(2), "name": m.group(3).strip(),
                      "description": m.group(4).strip()})
    return cards


def jack() -> dict | None:
    """JACK 音频服务是否在运行，以及它打开的设备、采样率和缓冲设置（从 jackd 的命令行读出）。"""
    if not Path("/proc").is_dir():
        return None
    found = _process("jackd")
    if found is None:
        return {"running": False}
    info = parse_jack_args(found[1])
    info["startedAt"] = _started_at(found[0])
    return info


def _split_short_options(args: list[str]) -> list[str]:
    """把连写的短选项拆开：``-dalsa`` → ``-d alsa``，``-r44100`` → ``-r 44100``（jackd 两种写法都接受）。"""
    out = []
    for a in args:
        if len(a) > 2 and a[0] == "-" and a[1] != "-" and a[1].isalpha():
            out += [a[:2], a[2:]]
        else:
            out.append(a)
    return out


def parse_jack_args(args: list[str]) -> dict:
    """从 jackd 的命令行读出驱动、设备、采样率和缓冲；``-d`` 之前是服务器选项，之后是驱动选项。"""
    info: dict = {"running": True, "device": None, "rate": None, "period": None, "periods": None}
    args = _split_short_options(args)
    if "-d" not in args:
        return info
    i = args.index("-d")
    driver = args[i + 1] if i + 1 < len(args) else None
    driver_args = args[i + 2:]
    for j, a in enumerate(driver_args):
        nxt = driver_args[j + 1] if j + 1 < len(driver_args) else None
        if a in ("-d", "--device", "-P", "--playback") and nxt:
            info["device"] = nxt
        elif a in ("-r", "--rate") and nxt:
            info["rate"] = int(nxt)
        elif a in ("-p", "--period") and nxt:
            info["period"] = int(nxt)
        elif a in ("-n", "--nperiods") and nxt:
            info["periods"] = int(nxt)
    if driver == "dummy":
        info["device"] = "dummy"
    return info


def output_device(jack_info: dict | None, cards: list[dict] | None) -> dict | None:
    """合成器服务实际使用的输出设备：JACK 打开的 ALSA 设备对应的声卡名字。"""
    if not jack_info or not jack_info.get("running"):
        return None
    dev = jack_info.get("device")
    if not dev:
        return None
    if dev == "dummy":
        return {"name": "虚拟设备（dummy）", "usb": False}
    m = re.match(r"hw:(?:CARD=)?([^,]+)", dev)
    card = None
    if m and cards:
        key = m.group(1)
        card = next((c for c in cards if str(c["index"]) == key or c["id"] == key), None)
    name = card["name"] if card else dev
    usb = "usb" in name.lower() or (card is not None and "usb" in card["description"].lower())
    return {"name": name, "usb": usb}


def xruns_since(since: float) -> int | None:
    """从 ``since``（Unix 时间）起的音频卡顿次数：从 systemd journal 里 jackd 的 xrun 记录数出来。"""
    out = _run(["journalctl", "--since", f"@{int(since)}", "--no-pager", "-o", "cat", "_COMM=jackd"], timeout=3)
    if out is None:
        return None
    return sum(1 for line in out.splitlines() if "xrun" in line.lower())


def synth_late_last_minute() -> int | None:
    """最近 1 分钟合成器服务收到得太晚的指令数：scsynth 每遇到一条就在日志里写一行 ``late <秒>``。

    太晚的指令只能在下一个音频缓冲执行，有节奏的声音因此忽早忽晚；主机程序自己看不到这件事。
    """
    out = _run(["journalctl", "--since", "-60s", "--no-pager", "-o", "cat", "_COMM=scsynth"], timeout=3)
    if out is None:
        return None
    return sum(1 for line in out.splitlines() if line.startswith("late "))


def machine(data_dir: Path) -> dict:
    info: dict = {"host": socket.gethostname(), "model": None, "tempC": None, "throttled": None,
                  "memUsedMB": None, "memTotalMB": None, "diskFreeGB": None, "diskTotalGB": None,
                  "uptime": None}
    model = _read("/proc/device-tree/model")
    if model:
        info["model"] = model.replace("\x00", "")
    t = _read("/sys/class/thermal/thermal_zone0/temp")
    if t and t.lstrip("-").isdigit():
        info["tempC"] = round(int(t) / 1000, 1)
    thr = _run(["vcgencmd", "get_throttled"])
    if thr and "=" in thr:
        info["throttled"] = int(thr.split("=")[1], 16) != 0
    mem = _read("/proc/meminfo")
    if mem:
        vals = {k: int(v.split()[0]) for k, v in (l.split(":", 1) for l in mem.splitlines() if ":" in l)}
        if "MemTotal" in vals and "MemAvailable" in vals:
            info["memTotalMB"] = round(vals["MemTotal"] / 1024)
            info["memUsedMB"] = round((vals["MemTotal"] - vals["MemAvailable"]) / 1024)
    try:
        path = data_dir if data_dir.exists() else data_dir.parent
        du = shutil.disk_usage(path)
        info["diskFreeGB"] = round(du.free / 1e9, 1)
        info["diskTotalGB"] = round(du.total / 1e9, 1)
    except OSError:
        pass
    up = _read("/proc/uptime")
    if up:
        info["uptime"] = int(float(up.split()[0]))
    return info


def network() -> dict:
    info: dict = {"name": None, "type": None, "address": None, "tailscale": None, "tailscaleAddress": None}
    out = _run(["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"])
    if out:
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) >= 3 and parts[1] in ("802-11-wireless", "802-3-ethernet", "wifi", "ethernet"):
                info["name"], info["type"] = parts[0], ("wifi" if "11" in parts[1] or parts[1] == "wifi" else "ethernet")
                break
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))     # 不发送任何数据，只为得到出口地址
        addr = s.getsockname()[0]
        s.close()
        if not addr.startswith("127."):
            info["address"] = addr
    except OSError:
        pass
    ts = _run(["tailscale", "status", "--json"], timeout=3)
    if ts:
        try:
            data = json.loads(ts)
            info["tailscale"] = data.get("BackendState")
            ips = (data.get("Self") or {}).get("TailscaleIPs") or []
            info["tailscaleAddress"] = next((ip for ip in ips if "." in ip), None)
        except ValueError:
            pass
    return info


def local_name(host: str | None) -> str | None:
    """局域网里的名字：主机名加 ``.local``；macOS 的主机名本身常带 ``.local``，不再重复。"""
    if not host:
        return None
    return host if host.lower().endswith(".local") else f"{host}.local"


def systemd_restarts(service: str) -> int | None:
    """主机程序被 systemd 自动重启的次数（NRestarts）。不在 systemd 下运行时为 None。"""
    if not os.environ.get("INVOCATION_ID"):      # systemd 启动的进程才有这个环境变量
        return None
    out = _run(["systemctl", "show", "-p", "NRestarts", "--value", service])
    if out is None or not out.strip().isdigit():
        return None
    return int(out.strip())


def version(root: Path) -> dict | None:
    """当前运行的程序版本。先读部署时写入的 VERSION 文件（第一行提交号，第二行部署时间），
    没有时用 git 读当前提交（有未提交的改动时标出）。都没有时为 None。"""
    text = _read(str(root / "VERSION"))
    if text:
        lines = text.splitlines()
        return {"commit": lines[0].strip(), "deployedAt": lines[1].strip() if len(lines) > 1 else None,
                "branch": lines[2].strip() if len(lines) > 2 else None, "dirty": None, "source": "deploy"}
    if not (root / ".git").exists():
        return None
    commit = _run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"])
    if not commit:
        return None
    status = _run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"])
    branch = _run(["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"])
    return {"commit": commit.strip(), "deployedAt": None, "branch": branch.strip() if branch else None,
            "dirty": bool(status and status.strip()), "source": "git"}


def ap_clients(interface: str) -> int | None:
    """自建热点上连着的设备数：内核邻居表里这个网卡上仍有效的条目（约数，离开的设备几分钟后才消失）。"""
    out = _run(["ip", "-4", "neigh", "show", "dev", interface])
    if out is None:
        return None
    return parse_neigh(out)


def parse_neigh(text: str) -> int:
    alive = ("REACHABLE", "STALE", "DELAY", "PROBE")
    return sum(1 for line in text.splitlines() if "lladdr" in line and line.split()[-1] in alive)


def network_kind(n: dict, phone_hotspot: str, self_hotspot: str) -> str | None:
    """连接类型：phoneHotspot（手机热点）、selfHotspot（自建热点）、external（其他 Wi-Fi）、wired（网线）。"""
    name, kind = n.get("name"), n.get("type")
    if name is None:
        return None
    if kind == "ethernet":
        return "wired"
    if name == phone_hotspot:
        return "phoneHotspot"
    if name == self_hotspot:
        return "selfHotspot"
    return "external"


def process_cpu_seconds() -> float:
    """本进程（主机程序，含所有线程）累计用掉的 CPU 时间（秒）。"""
    t = os.times()
    return t.user + t.system


def system_cpu_ticks() -> tuple[int, int] | None:
    """整机 CPU 的（忙碌, 总计）累计节拍数，来自 /proc/stat；不是 Linux 时为 None。"""
    text = _read("/proc/stat")
    if not text or not text.startswith("cpu "):
        return None
    vals = [int(x) for x in text.splitlines()[0].split()[1:]]
    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)      # idle + iowait
    return sum(vals) - idle, sum(vals)
