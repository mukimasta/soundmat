"""感知：全系统唯一理解垫面的地方，对外提供标准化输出（ARCHITECTURE「感知」）。

两级：垫面信号（``signal``，原始读数 → 压力图）和垫面解读（``interpret``，压力图 → 状态与事件）。
虚拟垫子（``virtual``）在开发时代替垫面信号。
"""
from __future__ import annotations

import threading

from ..config import MatConfig
from ..exchange import EventHub, Latest
from ..rates import RateMeter
from .interpret import Interpreter
from .model import MatEvent, MatSnapshot, PressureMap, empty_snapshot
from .virtual import HZ as VIRTUAL_HZ


class Perception:
    """接收压力图，更新垫面快照（最新值），把事件发给每个订阅者（事件队列）。"""

    def __init__(self, cfg: MatConfig, source: str = "controller"):
        self.source = source
        self.interpreter = Interpreter(cfg.occupancy_threshold, cfg.occupy_hold, cfg.release_hold)
        self.snapshot: Latest[MatSnapshot] = Latest(empty_snapshot(source=source))
        self.events: EventHub[MatEvent] = EventHub()
        self._lock = threading.Lock()
        self.rate = RateMeter()          # 实际完成垫面解读的帧率

    def rates(self) -> dict[str, dict]:
        """给系统监测：虚拟垫子按固定帧率产生压力图；控制器的帧率由它自己决定，没有期望值。"""
        return {"perception": {"actual": self.rate.rate(),
                               "expected": VIRTUAL_HZ if self.source == "virtual" else None}}

    def set_control_zones(self, zones) -> None:
        with self._lock:
            self.interpreter.set_control_zones(zones)

    def feed(self, pressure: PressureMap) -> None:
        self.rate.tick()
        with self._lock:
            state, events, features = self.interpreter.update(pressure)
        self.snapshot.set(MatSnapshot(pressure=pressure, state=state, features=features, source=self.source))
        self.events.publish(events)
