"""垫面解读：在压力图之上判断哪里有石头、发生了什么（ARCHITECTURE「感知」）。

石头由 ``stones`` 跟踪：直接从压力图找出石头、跨帧对上号，给出放下、拿起和挪动。这里在它之上
给出垫面状态（每颗石头的主区作为被占用的区、每环石头数、控制区压力）、静下来事件和可插拔的特征
（DATA_MODEL「垫面状态」「垫面事件」）。判断按压力图到达的时刻计算；控制器断线、没有新压力图时，
状态保持不变。
"""
from __future__ import annotations

from typing import Any, Protocol

import numpy as np

from ..model import MatEvent, MatState, PressureMap
from ..zones import NUM_RINGS, NUM_ZONES, ZONES
from .stones import Stone, StoneTracker, TrackerParams

__all__ = ["FeatureExtractor", "Interpreter", "Stone", "TrackerParams"]

_RING_OF = np.array([z.ring for z in ZONES], dtype=np.int64)


class FeatureExtractor(Protocol):
    """可插拔的特征提取器。每加一种特征，先说明它服务哪条 Design 要求。"""
    name: str

    def compute(self, pressure: PressureMap, state: MatState) -> Any: ...


class Interpreter:
    def __init__(self, params: TrackerParams, settle: float = 3.0):
        """``settle``：放下、拿起、挪动都停下这么多秒后，发出一次"静下来"。"""
        self.tracker = StoneTracker(params)
        self.settle = float(settle)
        self._last_activity: float | None = None
        self._settled = True              # 还没有任何动作时不发"静下来"
        self._control_mask: np.ndarray | None = None
        self.extractors: list[FeatureExtractor] = []

    def set_control_zones(self, zones: set[int] | frozenset[int] | None) -> None:
        """当前模式声明的控制区；None 表示不计算控制区压力。"""
        if not zones:
            self._control_mask = None
            return
        mask = np.zeros(NUM_ZONES, dtype=bool)
        mask[list(zones)] = True
        self._control_mask = mask

    def reset(self) -> None:
        self.tracker.reset()
        self._last_activity = None
        self._settled = True

    def update(self, pressure: PressureMap) -> tuple[MatState, list[MatEvent], dict[str, Any]]:
        t = pressure.t
        events = self.tracker.update(t, pressure.values)
        if events:
            self._last_activity = t
            self._settled = False
        elif not self._settled and self._last_activity is not None and t - self._last_activity >= self.settle:
            events.append(MatEvent(kind="settle", zone=None, t=t))
            self._settled = True

        stones = self.tracker.stones
        occupied = frozenset(s.zone for s in stones)
        counts = np.bincount(_RING_OF[list(occupied)], minlength=NUM_RINGS) if occupied else np.zeros(NUM_RINGS)
        control = None
        if self._control_mask is not None:
            control = float(pressure.values[self._control_mask].sum())
        state = MatState(
            t=t,
            occupied=occupied,
            ring_counts=tuple(int(c) for c in counts),
            control_pressure=control,
            stones=stones,
        )
        features = {fx.name: fx.compute(pressure, state) for fx in self.extractors}
        return state, events, features
