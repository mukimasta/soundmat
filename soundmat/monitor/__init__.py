"""系统监测：持续检查整台机器是否处在能正常演奏的状态（ARCHITECTURE「系统监测」）。

每秒采集一次：音频链路（音频服务、声卡、合成器服务、音色与素材、卡顿、负载、声部）、控制器链路、
机器、网络和当前状态，写入状态中心；再按规则给出声音、垫子、网络三个状态指示（正常、需要注意、
异常、未知）和原因。指示变化时写一条警告或错误到最近的记录。采集不到的项写成 None（未知），
不沿用旧值。
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..config import Config
from ..store import Store
from . import probes
from .log import EventLog

log = logging.getLogger("soundmat.monitor")

OK, WARN, ERROR, UNKNOWN = "ok", "warn", "error", "unknown"
SEVERITY = {OK: 0, UNKNOWN: 1, WARN: 2, ERROR: 3}
PEAK_LOAD_LIMIT = 85.0
LOW_FPS = 20.0
SLOW_PROBE_PERIOD = 10.0      # 较慢的探针（journal、tailscale、nmcli）的间隔


@dataclass
class Probes:
    """可替换的探针，测试时换成假的。"""
    jack: Callable[[], dict | None] = probes.jack
    cards: Callable[[], list | None] = probes.sound_cards
    xruns: Callable[[], int | None] = probes.xruns_last_hour
    machine: Callable[[Path], dict] = probes.machine
    network: Callable[[], dict] = probes.network
    platform_linux: bool = Path("/proc").is_dir()


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
                 synth_status: Callable[[], dict | None], layout_channels: Callable[[], int],
                 probes_: Probes | None = None):
        self.config = config
        self.store = store
        self.events = events
        self.data_dir = data_dir
        self.synth_status = synth_status
        self.layout_channels = layout_channels
        self.probes = probes_ or Probes()
        self.started = time.time()
        self.load_history: deque[float] = deque(maxlen=60)
        self.fps_history: deque[float] = deque(maxlen=60)
        self._slow: dict = {}
        self._next_slow = 0.0
        self._last_levels: dict[str, str] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ── 采集 ────────────────────────────────────────────────────────────

    def collect(self, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        if now >= self._next_slow:
            self._next_slow = now + SLOW_PROBE_PERIOD
            self._slow = {"xruns": self.probes.xruns(), "network": self.probes.network()}
        jack = self.probes.jack()
        cards = self.probes.cards()
        out_dev = probes.output_device(jack, cards)
        synth = self.synth_status() or {}
        online = synth.get("online")
        if online:
            self.load_history.append(round(float(synth.get("avgCPU", 0.0)), 1))
        mat = self.store.get("status.mat") or {}
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
            "channels": self.layout_channels(),
            "buffer": None if not jack or not jack.get("running") or jack.get("period") is None
            else {"period": jack["period"], "periods": jack.get("periods"), "driver": "JACK"},
            "xruns": self._slow.get("xruns"),
            "loadHistory": list(self.load_history),
        }
        machine = self.probes.machine(self.data_dir)
        machine["programUptime"] = probes.program_uptime(self.started)
        network = self._slow.get("network") or {}
        host = machine.get("host")
        line_parts = [network.get("name") or None, f"{host}.local" if host else None]
        network["line"] = " · ".join(p for p in line_parts if p)
        return {"audio": audio, "machine": machine, "network": network, "matHistory": list(self.fps_history)}

    # ── 判断 ────────────────────────────────────────────────────────────

    def assess(self, data: dict) -> dict:
        snd = self._assess_sound(data["audio"])
        mat = self._assess_mat()
        net = self._assess_network(data["network"])
        worst = max((snd, mat, net), key=lambda i: SEVERITY[i.level])
        issues = [f"{label}：{i.reason}" for label, i in (("声音", snd), ("垫子", mat), ("网络", net))
                  if i.level in (WARN, ERROR) and i.reason]
        return {"sound": snd.to_json(), "mat": mat.to_json(), "net": net.to_json(),
                "overall": worst.level, "issues": issues}

    def _assess_sound(self, a: dict) -> Indicator:
        cfg = self.config.sound
        s = a["synth"]
        if s["online"] is False and not s.get("everOnline") and time.time() - self.started < 15:
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
        missing = self.store.get("status.audio.assets.missing") or []
        if missing:
            return Indicator(WARN, f"缺少 {len(missing)} 个声音素材")
        if (s.get("peakLoad") or 0) > PEAK_LOAD_LIMIT:
            return Indicator(WARN, f"合成器服务运算负载峰值 {s['peakLoad']:.0f}%，超过 {PEAK_LOAD_LIMIT:.0f}%")
        if a["xruns"]:
            return Indicator(WARN, f"最近一小时音频卡顿 {a['xruns']} 次")
        return Indicator(OK)

    def _assess_mat(self) -> Indicator:
        m = self.store.get("status.mat") or {}
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
        if not n:
            return Indicator(UNKNOWN)
        if not n.get("address"):
            return Indicator(WARN, "没有连接任何网络，只能在本机查看控制台")
        return Indicator(OK)

    # ── 循环 ────────────────────────────────────────────────────────────

    def step(self, now: float | None = None) -> dict:
        data = self.collect(now)
        health = self.assess(data)
        self.store.update({
            "status.audio.service": data["audio"]["service"],
            "status.audio.usbCard": data["audio"]["usbCard"],
            "status.audio.synth": data["audio"]["synth"],
            "status.audio.outputDevice": data["audio"]["outputDevice"],
            "status.audio.channels": data["audio"]["channels"],
            "status.audio.buffer": data["audio"]["buffer"],
            "status.audio.xruns": data["audio"]["xruns"],
            "status.audio.loadHistory": data["audio"]["loadHistory"],
            "status.matHistory": data["matHistory"],
            "status.machine": data["machine"],
            "status.network": data["network"],
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
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.step()
            except Exception:
                log.exception("系统监测出错")
            self._stop.wait(1.0)
