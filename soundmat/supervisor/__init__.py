"""运行管理：唯一能启动和停止其他模块的地方（ARCHITECTURE「灯光引擎、设备连接与运行管理」）。

它按顺序建立各模块并把它们连起来，协调编排切换，决定失败时重试、降级还是退出。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..clock import BeatClock, system_time
from ..config import Config
from ..control import ControlContext
from ..exchange import Latest
from ..monitor.log import EventLog
from ..perception import Perception
from ..perception.virtual import VirtualMat
from ..sonification import ModeFactory, Sonification
from ..sonification.intent import LightIntent
from ..sonification.mode import Arrangement, LoadError, ModeContext
from ..sound.backend import Backend, RecordingBackend
from ..sound.engine import SoundEngine
from ..sound.spatial import SpeakerLayout
from ..store import Store

log = logging.getLogger("soundmat")


@dataclass
class Options:
    virtual: bool = False
    backend: Backend | None = None        # 默认使用不发声的记录型引擎
    modes: dict[str, ModeFactory] = field(default_factory=dict)


class Supervisor:
    def __init__(self, config: Config, options: Options | None = None):
        self.config = cfg = config
        self.options = opts = options or Options()
        self.store = Store({
            "status": {
                "current": {"virtual": opts.virtual, "arrangement": None, "mode": None,
                            "modeStatus": None, "switching": None},
                "log": [],
            },
        })
        self.events = EventLog(self.store)
        source = "virtual" if opts.virtual else "controller"
        self.perception = Perception(cfg.mat, source=source)
        self.virtual: VirtualMat | None = VirtualMat(self.perception.feed) if opts.virtual else None

        self.backend: Backend = opts.backend or RecordingBackend()
        self.engine = SoundEngine(self.backend, cfg.sound, SpeakerLayout.preset("stereo"))
        self.light: Latest[LightIntent] = Latest(LightIntent())
        self.sonification = Sonification(
            self.engine, self.perception, self.store, self.events, self.light,
            modes=opts.modes, ctx=ModeContext(led_count=cfg.light.led_count),
            crossfade=cfg.sound.crossfade_seconds,
        )
        self.clock = BeatClock(cfg.sound.tick_hz, self.sonification.on_beat, name="sonification")
        self.control = ControlContext(
            config=cfg, store=self.store, mat=self.perception.snapshot, virtual=self.virtual,
        )

    def switch(self, arrangement: Arrangement) -> None:
        """加载并切换到一份编排；加载失败时保持当前编排，抛出 ``LoadError``。"""
        try:
            inst = self.sonification.prepare(arrangement)
        except LoadError as e:
            self.events.error(f"无法加载 {arrangement.title}：{e}")
            raise
        self.sonification.switch(inst)

    def start(self) -> None:
        if self.virtual:
            self.virtual.start()
            log.info("使用虚拟垫子")
        else:
            self.events.warning("控制器连接尚未实现，请用 --virtual 运行")
        self.clock.start()

    def stop(self) -> None:
        self.clock.stop()
        if self.virtual:
            self.virtual.stop()

    def now(self) -> float:
        return system_time()
