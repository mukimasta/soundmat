"""感知：全系统唯一理解垫面的地方，对外提供标准化输出（ARCHITECTURE「感知」）。

两级：垫面信号（``signal``，原始读数 → 压力图）和垫面解读（``interpret``，压力图 → 石头、状态与事件）。
虚拟垫子（``virtual``）在开发时代替垫面信号。
"""
from __future__ import annotations

import threading

import numpy as np

from ..config import MatConfig
from ..exchange import EventHub, Latest
from ..rates import RateMeter
from .interpret import Interpreter, TrackerParams
from .model import MatEvent, MatSnapshot, PressureMap, empty_snapshot
from .signal import WIRE_SLICES, zone_wire_index
from .virtual import HZ as VIRTUAL_HZ
from .zones import INNER_RINGS, ZONES

_INNER = np.array([z.ring < INNER_RINGS for z in ZONES])


def tracker_params(cfg: MatConfig) -> TrackerParams:
    """配置 → 石头跟踪的参数。扇区导电条按接线算：串扰只沿同一根条发生。"""
    return TrackerParams(
        place_threshold=np.where(_INNER, cfg.inner_occupancy_threshold, cfg.occupancy_threshold),
        strips=zone_wire_index(cfg.sector_mirror, cfg.sector_offset) % WIRE_SLICES,
        floor=cfg.floor_ratio,
        occupy_hold=cfg.occupy_hold,
        release_hold=cfg.release_hold,
        release_hold_moving=cfg.release_hold_moving,
        crosstalk=cfg.crosstalk,
    )


class Perception:
    """接收压力图，更新垫面快照（最新值），把事件发给每个订阅者（事件队列）。

    要逐帧记录的使用者（录制）订阅 ``frames``，取到每一帧的快照；只读最新值会漏掉两次读取之间的帧。
    """

    def __init__(self, cfg: MatConfig, source: str = "controller"):
        self.source = source
        self.interpreter = Interpreter(tracker_params(cfg), settle=cfg.settle)
        self.snapshot: Latest[MatSnapshot] = Latest(empty_snapshot(source=source))
        self.frames: EventHub[MatSnapshot] = EventHub()
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
        snap = MatSnapshot(pressure=pressure, state=state, features=features, source=self.source)
        self.snapshot.set(snap)
        self.frames.publish([snap])
        self.events.publish(events)
