"""运行管理：唯一能启动和停止其他模块的地方（ARCHITECTURE「灯光引擎、设备连接与运行管理」）。

它按顺序建立各模块并把它们连起来，决定失败时重试、降级还是退出。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..config import Config
from ..control import ControlContext
from ..perception import Perception
from ..perception.virtual import VirtualMat
from ..store import Store

log = logging.getLogger("soundmat")


@dataclass
class Options:
    virtual: bool = False


@dataclass
class Supervisor:
    config: Config
    options: Options = field(default_factory=Options)

    def __post_init__(self):
        cfg = self.config
        self.store = Store({
            "status": {
                "current": {"virtual": self.options.virtual},
            },
        })
        source = "virtual" if self.options.virtual else "controller"
        self.perception = Perception(cfg.mat, source=source)
        self.virtual: VirtualMat | None = None
        if self.options.virtual:
            self.virtual = VirtualMat(self.perception.feed)
        self.control = ControlContext(
            config=cfg, store=self.store, mat=self.perception.snapshot, virtual=self.virtual,
        )

    def start(self) -> None:
        if self.virtual:
            self.virtual.start()
            log.info("使用虚拟垫子")
        else:
            log.warning("控制器连接尚未实现，请用 --virtual 运行")

    def stop(self) -> None:
        if self.virtual:
            self.virtual.stop()
