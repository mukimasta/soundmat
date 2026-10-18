"""维护：从控制台重启声音、主机程序或整台机器（design/CONSOLE.md「重启」）。

三种重启都交给 systemd（``systemctl --no-block``），从轻到重：

- ``sound``：重启 JACK 和合成器服务，声音中断约 5 秒；主机程序发现合成器服务重启后自己重建混音结构。
- ``program``：重启主机程序，声音和灯光中断约 15 秒，控制台断开后自动重连。
- ``machine``：重启整台树莓派，约 1 分钟后回来。

手动重启不会被 systemd 算进"自动重启"的次数，看板上的重启次数不受影响。装置用户需要系统权限规则
``system/polkit/50-soundmat.rules``。只有主机程序本身就是 ``soundmat.service`` 时（装置上）可用：
判断看自己所在的 cgroup，而不是"是否由 systemd 运行"——CI 的机器本身也由 systemd 运行，
那样判断会让测试真的去重启系统服务。
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from .errors import Conflict, InvalidRequest
from .monitor.log import EventLog
from .store import Store

TARGETS: dict[str, tuple[list[str], str]] = {
    "sound": (["restart", "jackd.service", "soundmat-scsynth.service"], "重启声音"),
    "program": (["restart", "soundmat.service"], "重启程序"),
    "machine": (["reboot"], "重启机器"),
}


SERVICE = "soundmat.service"


def running_as_service(cgroup: Path = Path("/proc/self/cgroup")) -> bool:
    """主机程序是不是作为 soundmat.service 运行（cgroup 形如 ``0::/system.slice/soundmat.service``）。"""
    try:
        return any(line.rstrip().endswith("/" + SERVICE) for line in cgroup.read_text().splitlines())
    except OSError:
        return False


def _systemctl(args: list[str]) -> None:
    p = subprocess.run(["systemctl", "--no-block", *args], capture_output=True, text=True, timeout=10)
    if p.returncode != 0:
        raise Conflict(f"systemd 拒绝了这次重启：{(p.stderr or p.stdout).strip()[-200:]}"
                       "（装置上需要安装 system/polkit/50-soundmat.rules）")


class Maintenance:
    def __init__(self, store: Store, events: EventLog, systemd: bool | None = None,
                 run: Callable[[list[str]], None] = _systemctl):
        self.events = events
        self.enabled = running_as_service() if systemd is None else systemd
        self.run = run
        store.writer("status.maintenance").set("status.maintenance", {"enabled": self.enabled})

    def restart(self, target: str) -> None:
        """按 ``target``（sound / program / machine）重启。不能重启时抛出给人看的错误。"""
        if target not in TARGETS:
            raise InvalidRequest(f"不认识的重启对象：{target}")
        if not self.enabled:
            raise Conflict("只有装置上（由 systemd 运行时）才能从控制台重启")
        args, label = TARGETS[target]
        self.events.warning(f"从控制台{label}")
        self.run(args)
