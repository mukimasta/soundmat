"""运行管理：唯一建立、连接、启动和停止其他模块的地方（ARCHITECTURE「灯光引擎、设备连接与运行管理」）。

它只做三件事：按依赖顺序建立各模块并把它们连起来；把设置的变化转给相应的模块；按顺序启动
各个服务、按相反的顺序停止。具体的事情都在各模块里：编排目录在 ``sonification/catalog.py``，
各模块的运行数据由模块自己提供给系统监测（``monitor.Sources``），状态树每段由谁写见
``store/branches.py``。
"""
from __future__ import annotations

import logging
import os
import signal
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from ..clock import BeatClock
from ..config import ROOT, Config
from ..control import ControlContext
from ..device import DeviceLink, RawFrame
from ..exchange import Latest
from ..intent import LightIntent
from ..light import LightEngine
from ..maintenance import Maintenance
from ..monitor import Monitor, Probes, Sources
from ..monitor import probes
from ..monitor.log import EventLog
from ..periodic import Periodic
from ..perception import Perception
from ..perception.signal import Signal
from ..perception.virtual import VirtualMat
from ..recorder import Recorder
from ..sonification import ModeFactory, Sonification
from ..sonification.ambient import AmbientMode
from ..sonification.arrangements import ARRANGEMENTS_DIR
from ..sonification.catalog import Catalog
from ..sonification.jam import JamMode
from ..sonification.mode import ModeContext
from ..sound.assets import AssetLibrary
from ..sound.backend import Backend, RecordingBackend
from ..sound.engine import SoundEngine
from ..sound.scsynth import ScsynthBackend
from ..sound.spatial import SpeakerLayout
from ..store import Store
from ..store.settings import Settings
from ..updater import Updater, detect_layout

log = logging.getLogger("soundmat")

MODES: dict[str, ModeFactory] = {"ambient": AmbientMode, "jam": JamMode}
LEVELS_PERIOD = 0.1    # 秒：电平采样的间隔（只供控制台显示）


class Service(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...


def _exit_for_restart() -> None:
    """更新切换版本后：让主机程序正常退出，systemd（Restart=always）按 current 指向的新版本重新启动。"""
    threading.Timer(0.5, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()


@dataclass
class Options:
    virtual: bool = False
    backend: Backend | None = None        # 默认使用不发声的记录型引擎
    modes: dict[str, ModeFactory] = field(default_factory=lambda: dict(MODES))
    data_dir: Path = ROOT / "data"
    serial_port: str = "auto"
    synth: str = "recording"              # recording（不发声）或 scsynth
    probes: Probes | None = None          # 系统监测的探针，测试时注入
    monitor: bool = True
    device: DeviceLink | None = None      # 测试时注入模拟控制器
    arrangements_dir: Path = ARRANGEMENTS_DIR
    seed: int | None = None
    restart: Callable[[], None] | None = None   # 更新后重新启动主机程序；默认让进程退出、由 systemd 拉起


class Supervisor:
    def __init__(self, config: Config, options: Options | None = None):
        self.config = cfg = config
        self.options = opts = options or Options()
        self.store = Store()
        self.events = EventLog(self.store)
        self.settings = Settings(self.store, opts.data_dir)

        # 感知与输入
        self.perception = Perception(cfg.mat, source="virtual" if opts.virtual else "controller")
        self.signal = Signal(cfg.mat)
        self.virtual: VirtualMat | None = None
        self.device: DeviceLink | None = None
        if opts.virtual:
            self.virtual = VirtualMat(self.perception.feed)
        else:
            self.device = opts.device or DeviceLink(self._on_raw_frame, port=opts.serial_port,
                                                    on_event=self._device_event)

        # 声音
        if opts.backend is not None:
            self.backend: Backend = opts.backend
        elif opts.synth == "scsynth":
            self.backend = ScsynthBackend(cfg.synth.host, cfg.synth.port, cfg.synth.synthdefs_path,
                                          resolve_asset=lambda ref: self.assets.info(ref))
        else:
            self.backend = RecordingBackend()
        self.engine = SoundEngine(self.backend, cfg.sound, self._layout(), self.settings.get("sound.orientation", 0.0))
        self.assets = AssetLibrary(Path(self.settings.get("run.soundLibrary")), cfg.sound.asset_memory_mb, self.backend)
        self.engine.on_rebuild.append(self.assets.reload_all)

        # 声音化、灯光与录制
        self.light_intent: Latest[LightIntent] = Latest(LightIntent())
        self.sonification = Sonification(
            self.engine, self.assets, self.perception, self.store, self.events, self.light_intent,
            modes=opts.modes,
            ctx=ModeContext(led_count=cfg.light.led_count, setting=self.settings.get, seed=opts.seed,
                            heard_after=cfg.sound.schedule_ahead),
            crossfade=cfg.sound.crossfade_seconds,
        )
        self.catalog = Catalog(self.store, self.events, self.sonification, self.assets, opts.arrangements_dir)
        self.clock = BeatClock(cfg.sound.tick_hz, self.sonification.on_beat, name="sonification",
                               stall_after=cfg.sound.late_tolerance)
        self.lights = LightEngine(cfg.light, self.light_intent, send=self.device.send_leds if self.device else None)
        self.recorder = Recorder(self.store, self.events, self.settings, self.sonification, self.perception,
                                 self.lights, cfg)

        # 管理与控制
        version = probes.version(ROOT)
        self.updater = Updater(self.store, self.events, cfg.update.repo, opts.data_dir,
                               version["commit"] if version else None, layout=detect_layout(),
                               restart=opts.restart or _exit_for_restart)
        self.maintenance = Maintenance(self.store, self.events)
        self.control = ControlContext(
            config=cfg, store=self.store, mat=self.perception.snapshot, settings=self.settings,
            play=self.catalog.play, test_tone=self.test_tone, recorder=self.recorder, updater=self.updater,
            maintenance=self.maintenance,
            virtual=self.virtual,
            streams={"leds": self.lights.preview, "levels": self.sonification.levels},
        )
        link = self.virtual or self.device
        self.monitor = Monitor(cfg, self.store, self.events, opts.data_dir, probes_=opts.probes, sources=Sources(
            synth=self.backend.status,
            channels=lambda: self.engine.layout.channels,
            mat=link.status,
            rates=[r for r in (self.device, self.perception, self.clock, self.lights, self.control) if r is not None],
            counters=[self.clock, self.engine],
            beat_lag=self.clock.max_lag,
            storage=self.recorder,
        ))

        self.store.subscribe(self._on_change)
        self.sonification.run_in_beat(self._apply_sound_settings)

        # 按顺序启动、按相反的顺序停止
        self.services: list[Service] = [
            link, self.clock, self.lights,
            Periodic("levels", LEVELS_PERIOD, self.sonification.sample_levels),
            self.updater,
            *([self.monitor] if opts.monitor else []),
        ]

    # ── 启动与停止 ──────────────────────────────────────────────────────

    def start(self) -> None:
        self.catalog.play_default(self.settings.get("run.defaultArrangement"))
        for s in self.services:
            s.start()

    def stop(self) -> None:
        for s in reversed(self.services):
            s.stop()

    # ── 连接 ────────────────────────────────────────────────────────────

    def _on_raw_frame(self, frame: RawFrame) -> None:
        self.perception.feed(self.signal.pressure(frame.t, frame.seq, frame.values))

    def _device_event(self, level: str, text: str) -> None:
        getattr(self.events, level)(text)

    def test_tone(self, channel: int) -> None:
        """控制台的逐声道测试音：先检查声道，再交给节拍线程（声音引擎只在那里调用）。"""
        self.engine.check_channel(channel)
        self.sonification.run_in_beat(lambda now: self.engine.test_tone(channel, now))

    # ── 设置 ────────────────────────────────────────────────────────────

    def _layout(self) -> SpeakerLayout:
        return SpeakerLayout.from_json(self.settings.get("sound.layout"))

    def _on_change(self, changes) -> None:
        paths = [p for p, _ in changes]
        if any(p.startswith("settings.sound") for p in paths):
            self.sonification.run_in_beat(self._apply_sound_settings)
        if "settings.run.soundLibrary" in paths:
            self.assets.set_root(Path(self.settings.get("run.soundLibrary")))
            self.catalog.refresh()

    def _apply_sound_settings(self, now: float) -> None:
        self.engine.set_master({"volume": float(self.settings.get("sound.volume", 0.8))}, now)
        layout = self._layout()
        orientation = float(self.settings.get("sound.orientation", 0.0))
        if layout != self.engine.layout or orientation != self.engine.orientation:
            self.engine.set_layout(layout, orientation, now)
