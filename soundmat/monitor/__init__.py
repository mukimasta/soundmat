"""系统监测：持续检查整台机器是否处在能正常演奏的状态（ARCHITECTURE「系统监测」）。

每秒采集一次：音频链路（音频服务、声卡、合成器服务、音色与素材、卡顿、负载、声部）、控制器链路、
各条链路的实际帧率与计时（节拍超时、迟到）、主机程序（运行时间、自动重启、版本）、机器、网络、
录音空间和当前状态，写入状态中心；再按规则给出声音、垫子、网络三个状态指示（正常、需要注意、
异常、未知）和原因。指示变化时写一条警告或错误到最近的记录。采集不到的项写成 None（未知），
不沿用旧值。

各模块的运行数据由模块自己提供（``Sources``：每个模块的 ``rates()``、``counters()``、``status()``），
系统监测只负责采集、判断和写入自己的那几段状态（见 store/branches.py）。较慢的探针
（journal、nmcli、systemctl、git）在单独的线程里每 10 秒运行一次，不拖慢每秒一次的采集。
"""
from __future__ import annotations

import json
import os
import shutil
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, Sequence

from ..config import ROOT, Config
from ..periodic import Periodic
from ..store import Store
from ..timebase import system_time
from . import probes
from .log import EventLog


OK, WARN, ERROR, UNKNOWN = "ok", "warn", "error", "unknown"
SEVERITY = {OK: 0, UNKNOWN: 1, WARN: 2, ERROR: 3}
PEAK_LOAD_LIMIT = 85.0
LOW_FPS = 20.0
SLOW_PROBE_PERIOD = 10.0
XRUN_WINDOW = 3600.0          # 秒：卡顿最多统计这么久（主机程序或 JACK 启动不到这么久时，从启动算起）      # 较慢的探针（journal、tailscale、nmcli、systemctl、git）的间隔
RECENT = 60.0                 # 秒：「最近 1 分钟」的节拍超时与迟到
RESTART_WINDOW = 3600.0       # 秒：主机程序这么久之内被自动重启过，记为需要注意
PROGRAM_CPU_LIMIT = 90.0      # 主机程序最近 10 秒平均占单核的百分比达到这个值：需要注意
# 最近 1 分钟节拍「卡住」（晚到超过迟到容忍度）达到这个次数才提示；偶尔一次（例如切换编排）不提示。
STALL_WARN = 3
# 最近 1 分钟合成器服务收到太晚的指令达到这个数：节奏可能不稳（偶尔一两条，例如刚启动时，不提示）
SYNTH_LATE_WARN = 5


@dataclass
class Probes:
    """可替换的探针，测试时换成假的。"""
    jack: Callable[[], dict | None] = probes.jack
    cards: Callable[[], list | None] = probes.sound_cards
    xruns: Callable[[float], int | None] = probes.xruns_since
    synth_late: Callable[[], int | None] = probes.synth_late_last_minute
    clock: Callable[[], bool | None] = probes.clock_status
    machine: Callable[[Path], dict] = probes.machine
    network: Callable[[], dict] = probes.network
    restarts: Callable[[str], int | None] = probes.systemd_restarts
    version: Callable[[Path], dict | None] = probes.version
    ap_clients: Callable[[str], int | None] = probes.ap_clients
    process_cpu: Callable[[], float] = probes.process_cpu_seconds
    system_cpu: Callable[[], tuple[int, int] | None] = probes.system_cpu_ticks
    platform_linux: bool = Path("/proc").is_dir()


class RateSource(Protocol):
    def rates(self) -> dict[str, dict]: ...          # 链路 → {actual, expected}


class CounterSource(Protocol):
    def counters(self) -> dict[str, int]: ...        # 启动以来的累计数


class StorageSource(Protocol):
    root: Path                                        # 录音保存位置
    def bytes_per_second(self) -> int: ...            # 录音每秒写入的字节数，不录音频时为 0


@dataclass
class Sources:
    """系统监测从各模块读取的运行数据。每一项都可以在任意线程调用。"""
    synth: Callable[[], dict | None] = lambda: None           # 合成器服务（Backend.status）
    channels: Callable[[], int] = lambda: 2                   # 当前音箱数
    mat: Callable[[], dict] = lambda: {}                      # 控制器链路（DeviceLink / VirtualMat 的 status）
    rates: Sequence[RateSource] = ()
    counters: Sequence[CounterSource] = ()
    beat_lag: Callable[[], float] = lambda: 0.0              # 最近 1 分钟最大的节拍延迟（秒）
    storage: StorageSource | None = None


@dataclass
class Indicator:
    level: str
    reason: str = ""

    def to_json(self) -> dict:
        return {"level": self.level, "reason": self.reason}


def _rate_text(hz: float) -> str:
    return f"{hz / 1000:g} kHz"


class Monitor:
    def __init__(self, config: Config, store: Store, events: EventLog, data_dir: Path,
                 sources: Sources | None = None, probes_: Probes | None = None):
        self.config = config
        self.state = store.writer("status.health", "status.mat", "status.matHistory", "status.audio",
                                  "status.machine", "status.network", "status.rates", "status.timing",
                                  "status.program", "status.storage")
        self.events = events
        self.data_dir = data_dir
        self.sources = sources or Sources()
        self.probes = probes_ or Probes()
        self._counters: deque[tuple[float, dict]] = deque()
        self.started = system_time()
        self.started_wall = time.time()
        self.load_history: deque[float] = deque(maxlen=60)
        self.fps_history: deque[float] = deque(maxlen=60)
        self.program_cpu_history: deque[float] = deque(maxlen=60)
        self._last_cpu: tuple[float, float] | None = None          # (时刻, 本进程 CPU 秒)
        self._last_ticks: tuple[int, int] | None = None            # 整机（忙碌, 总计）
        self._slow: dict = {}
        self._next_slow = 0.0
        self._last_levels: dict[str, str] = {}
        self._loops: list[Periodic] = []

    def uptime(self) -> int:
        return int(system_time() - self.started)

    # ── 采集 ────────────────────────────────────────────────────────────

    def refresh_slow(self, now: float | None = None) -> None:
        """较慢的探针：最近一小时的卡顿、网络、systemd 重启次数、版本。"""
        # 卡顿从主机程序和 JACK 里较晚的那次启动算起、最长一小时：重启之前的卡顿不再算作现在的问题
        hour_ago = time.time() - XRUN_WINDOW
        jack = self.probes.jack() or {}
        since = max(hour_ago, self.started_wall, jack.get("startedAt") or 0)
        self._slow = {"xruns": self.probes.xruns(since), "xrunsSinceStart": since > hour_ago,
                      "synthLate": self.probes.synth_late(),
                      "network": self.probes.network(),
                      "restarts": self.probes.restarts(self.config.system.service),
                      "version": self.probes.version(ROOT)}

    def collect(self, now: float | None = None) -> dict:
        now = system_time() if now is None else now
        if not self._loops and now >= self._next_slow:      # 没有单独的线程时（测试）在这里顺便运行
            self._next_slow = now + SLOW_PROBE_PERIOD
            self.refresh_slow(now)
        src = self.sources
        jack = self.probes.jack()
        cards = self.probes.cards()
        out_dev = probes.output_device(jack, cards)
        synth = src.synth() or {}
        online = synth.get("online")
        if online:
            self.load_history.append(round(float(synth.get("avgCPU", 0.0)), 1))
        mat = src.mat()
        if mat.get("fps") is not None:
            self.fps_history.append(mat["fps"])

        audio = {
            "service": None if jack is None else jack.get("running"),
            "usbCard": None if cards is None else any("usb" in (c["name"] + c["description"]).lower() for c in cards),
            "synth": {
                "online": bool(online) if synth else None,
                "everOnline": synth.get("everOnline"),
                "synthdefsLoaded": synth.get("synthdefsLoaded"),
                "sampleRate": synth.get("nominalSampleRate"),
                "avgLoad": synth.get("avgCPU"),
                "peakLoad": synth.get("peakCPU"),
            },
            "outputDevice": out_dev,
            "channels": src.channels(),
            "buffer": None if not jack or not jack.get("running") or jack.get("period") is None
            else {"period": jack["period"], "periods": jack.get("periods"), "driver": "JACK"},
            "xruns": self._slow.get("xruns"),
            "xrunsSinceStart": self._slow.get("xrunsSinceStart"),
            "loadHistory": list(self.load_history),
        }
        machine = self.probes.machine(self.data_dir)
        machine.update(self._cpu(now))
        machine["cores"] = os.cpu_count()
        machine["programUptime"] = self.uptime()
        machine["clockSynced"] = self.probes.clock()
        network = dict(self._slow.get("network") or {})
        network["localName"] = probes.local_name(machine.get("host"))
        network["line"] = " · ".join(p for p in (network.get("name"), network["localName"]) if p)
        ncfg = self.config.network
        network["kind"] = probes.network_kind(network, ncfg.phone_hotspot, ncfg.self_hotspot)
        network["apClients"] = self.probes.ap_clients(ncfg.interface) if network["kind"] == "selfHotspot" else None

        rates: dict[str, dict] = {}
        for r in src.rates:
            rates.update(r.rates())
        counters: dict[str, int] = {}
        for c in src.counters:
            counters.update(c.counters())
        timing = self._timing(now, counters)
        timing["maxLagMs"] = round(src.beat_lag() * 1000, 1)
        timing["synthLate"] = self._slow.get("synthLate")
        timing["synthLateAttention"] = (timing["synthLate"] or 0) >= SYNTH_LATE_WARN
        program = {"uptime": self.uptime(), "restarts": self._slow.get("restarts"),
                   "version": self._slow.get("version"), "plannedStart": self._planned_start()}
        return {"audio": audio, "mat": mat, "machine": machine, "network": network,
                "matHistory": list(self.fps_history), "rates": rates, "timing": timing,
                "program": program, "storage": self._storage()}

    def _timing(self, now: float, counters: dict) -> dict:
        """累计数和最近 1 分钟内的增加量（节拍超时、迟到丢弃、声部让位、因预算放弃）。"""
        self._counters.append((now, dict(counters)))
        # 基准是 1 分钟前（或更早）的最后一个样本，这样窗口里发生的增加一次都不漏
        while len(self._counters) > 1 and self._counters[1][0] <= now - RECENT:
            self._counters.popleft()
        oldest = self._counters[0][1]
        out: dict = {}
        for k, v in counters.items():
            out[k] = v
            out[f"{k}Recent"] = None if oldest.get(k) is None else v - oldest[k]
        out["stallsAttention"] = (out.get("stallsRecent") or 0) >= STALL_WARN
        out["lateAttention"] = bool(out.get("lateRecent"))
        return out

    def _cpu(self, now: float) -> dict:
        """主机程序的 CPU（占单核的百分比，可超过 100%）和整机 CPU（所有核的平均），按两次采集之间的增量算。"""
        out: dict = {"programCpu": None, "cpu": None, "programCpuHistory": list(self.program_cpu_history)}
        cpu_s = self.probes.process_cpu()
        if self._last_cpu is not None and now > self._last_cpu[0]:
            pct = round((cpu_s - self._last_cpu[1]) / (now - self._last_cpu[0]) * 100, 1)
            out["programCpu"] = pct
            self.program_cpu_history.append(pct)
            out["programCpuHistory"] = list(self.program_cpu_history)
        self._last_cpu = (now, cpu_s)
        ticks = self.probes.system_cpu()
        if ticks is not None and self._last_ticks is not None and ticks[1] > self._last_ticks[1]:
            busy, total = ticks[0] - self._last_ticks[0], ticks[1] - self._last_ticks[1]
            out["cpu"] = round(busy / total * 100, 1)
        self._last_ticks = ticks
        return out

    def _planned_start(self) -> bool:
        """这次启动是不是软件更新安排的（更新切换版本后主机程序有意退出，由 systemd 拉起）。"""
        try:
            planned = json.loads((self.data_dir / "update.json").read_text()).get("plannedAt")
        except (OSError, ValueError):
            return False
        return isinstance(planned, (int, float)) and 0 <= self.started_wall - planned < 120

    def _storage(self) -> dict:
        """录音空间：可用空间，以及按当前声道数和分轨设置估算还能录多少分钟（不录音频时为 None）。"""
        st = self.sources.storage
        free = None
        rate = 0
        if st is not None:
            rate = st.bytes_per_second()
            p = Path(st.root)
            while not p.exists() and p != p.parent:
                p = p.parent
            try:
                free = shutil.disk_usage(p).free
            except OSError:
                free = None
        return {"freeGB": None if free is None else round(free / 1e9, 1),
                "minutes": None if free is None or rate <= 0 else int(free / rate / 60)}

    # ── 判断 ────────────────────────────────────────────────────────────

    def assess(self, data: dict) -> dict:
        snd = self._assess_sound(data["audio"], data)
        mat = self._assess_mat(data["mat"])
        net = self._assess_network(data["network"])
        worst = max((snd, mat, net), key=lambda i: SEVERITY[i.level])
        issues = [f"{label}：{i.reason}" for label, i in (("声音", snd), ("垫子", mat), ("网络", net))
                  if i.level in (WARN, ERROR) and i.reason]
        return {"sound": snd.to_json(), "mat": mat.to_json(), "net": net.to_json(),
                "overall": worst.level, "issues": issues}

    def _assess_sound(self, a: dict, data: dict | None = None) -> Indicator:
        data = data or {}
        cfg = self.config.sound
        s = a["synth"]
        if s["online"] is False and not s.get("everOnline") and self.uptime() < 15:
            return Indicator(UNKNOWN, "正在连接合成器服务")
        if s["online"] is False:
            return Indicator(ERROR, "合成器服务没有响应，音箱不会发声")
        if s["online"] is None:
            return Indicator(UNKNOWN, "没有连接合成器服务（不发声的开发模式）")
        if s.get("synthdefsLoaded") is False:
            return Indicator(ERROR, "合成器服务没有加载音色，需要先编译音色")
        if self.probes.platform_linux and a["service"] is False:
            return Indicator(ERROR, "音频服务（JACK）没有运行")
        dev = a["outputDevice"]
        if cfg.expected_output_device.upper() == "USB" and dev is not None and not dev["usb"]:
            return Indicator(ERROR, f"合成器服务没有使用 USB 声卡，当前输出到 {dev['name']}，音箱不会发声")
        if cfg.expected_output_device.upper() == "USB" and a["usbCard"] is False:
            return Indicator(ERROR, "没有找到 USB 声卡")
        sr = s.get("sampleRate")
        if sr and abs(sr - cfg.expected_sample_rate) > 1:
            return Indicator(WARN, f"合成器服务的采样率是 {_rate_text(sr)}，期望 {_rate_text(cfg.expected_sample_rate)}")
        missing = self.state.get("status.assets.missing") or []
        if missing:
            return Indicator(WARN, f"缺少 {len(missing)} 个声音素材")
        if (s.get("peakLoad") or 0) > PEAK_LOAD_LIMIT:
            return Indicator(WARN, f"合成器服务运算负载峰值 {s['peakLoad']:.0f}%，超过 {PEAK_LOAD_LIMIT:.0f}%")
        if a["xruns"]:
            window = "启动以来" if a.get("xrunsSinceStart") else "最近一小时"
            return Indicator(WARN, f"{window}音频卡顿 {a['xruns']} 次")
        timing = self._indicate_timing(data)
        if timing is not None:
            return timing
        return Indicator(OK)

    def _indicate_timing(self, data: dict) -> Indicator | None:
        """节拍卡住、定时事件迟到、主机程序最近被自动重启：都会让声音不稳，记为需要注意。"""
        t = data.get("timing") or {}
        if t.get("stallsAttention"):
            return Indicator(WARN, f"最近 1 分钟声音化节拍有 {t['stallsRecent']} 次晚到超过 "
                                   f"{self.config.sound.late_tolerance * 1000:g} ms，定时声音可能迟到")
        if t.get("synthLateAttention"):
            return Indicator(WARN, f"最近 1 分钟合成器服务有 {t['synthLate']} 条指令收到得太晚，节奏可能不稳"
                                   "（定时声音提前量 sound.schedule_ahead 可能小于音频缓冲）")
        if t.get("lateAttention"):
            return Indicator(WARN, f"最近 1 分钟有 {t['lateRecent']} 个定时事件迟到被丢弃")
        recent = list(self.program_cpu_history)[-10:]
        if len(recent) >= 5 and sum(recent) / len(recent) >= PROGRAM_CPU_LIMIT:
            return Indicator(WARN, f"主机程序占满了一个 CPU 核（最近 10 秒平均 {sum(recent) / len(recent):.0f}%），"
                                   "声音和灯光可能不稳")
        p = data.get("program") or {}
        if (p.get("restarts") and p.get("uptime") is not None and p["uptime"] < RESTART_WINDOW
                and not p.get("plannedStart")):
            return Indicator(WARN, f"主机程序最近一小时内被自动重启过（共 {p['restarts']} 次），可能在反复出错")
        return None

    def _assess_mat(self, m: dict) -> Indicator:
        if m.get("source") == "virtual":
            return Indicator(OK, "使用虚拟垫子")
        if not m:
            return Indicator(UNKNOWN)
        if not m.get("connected"):
            return Indicator(ERROR, m.get("problem") or "控制器未连接")
        if m.get("fps") is not None and m["fps"] < LOW_FPS:
            return Indicator(WARN, f"传感帧率只有 {m['fps']:.0f} fps")
        return Indicator(OK)

    def _assess_network(self, n: dict) -> Indicator:
        if "address" not in n:              # 网络探针还没运行过（刚启动）
            return Indicator(UNKNOWN)
        if not n.get("address"):
            return Indicator(WARN, "没有连接任何网络，只能在本机查看控制台")
        return Indicator(OK)

    # ── 循环 ────────────────────────────────────────────────────────────

    def step(self, now: float | None = None) -> dict:
        data = self.collect(now)
        health = self.assess(data)
        audio = data["audio"]
        self.state.update({
            **{f"status.audio.{k}": audio[k] for k in ("service", "usbCard", "synth", "outputDevice", "channels",
                                                         "buffer", "xruns", "xrunsSinceStart", "loadHistory")},
            "status.mat": data["mat"],
            "status.matHistory": data["matHistory"],
            "status.machine": data["machine"],
            "status.network": data["network"],
            "status.rates": data["rates"],
            "status.timing": data["timing"],
            "status.program": data["program"],
            "status.storage": data["storage"],
            "status.health": health,
        })
        self._log_transitions(health)
        return health

    def _log_transitions(self, health: dict) -> None:
        for key, label in (("sound", "声音"), ("mat", "垫子"), ("net", "网络")):
            ind = health[key]
            prev = self._last_levels.get(key)
            sig = f"{ind['level']}:{ind['reason']}"
            if prev == sig:
                continue
            self._last_levels[key] = sig
            if ind["level"] == ERROR:
                self.events.error(f"{label}：{ind['reason']}")
            elif ind["level"] == WARN:
                self.events.warning(f"{label}：{ind['reason']}")
            elif prev is not None and ind["level"] == OK and prev.split(":")[0] in (WARN, ERROR):
                self.events.info(f"{label}：恢复正常")

    def start(self) -> None:
        self._loops = [Periodic("monitor-slow", SLOW_PROBE_PERIOD, self.refresh_slow),
                       Periodic("monitor", 1.0, self.step)]
        for loop in self._loops:
            loop.start()

    def stop(self) -> None:
        for loop in self._loops:
            loop.stop()
