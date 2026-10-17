"""垫面解读：在压力图之上判断哪里有石头、发生了什么（ARCHITECTURE「感知」）。

占用判定带去抖：一个区需要稳定高于阈值 ``occupy_hold`` 秒才算被占用，稳定低于阈值
``release_hold`` 秒才算释放（DATA_MODEL「垫面状态」）。去抖按压力图到达的时刻计算；
控制器断线、没有新压力图时，状态保持不变。
"""
from __future__ import annotations

from typing import Any, Protocol

import numpy as np

from ..model import MatEvent, MatState, PressureMap
from ..zones import NUM_RINGS, NUM_ZONES, ZONES

_RING_OF = np.array([z.ring for z in ZONES], dtype=np.int64)


class FeatureExtractor(Protocol):
    """可插拔的特征提取器。每加一种特征，先说明它服务哪条 Design 要求。"""
    name: str

    def compute(self, pressure: PressureMap, state: MatState) -> Any: ...


class Interpreter:
    def __init__(self, threshold: float, occupy_hold: float, release_hold: float):
        self.threshold = float(threshold)
        self.occupy_hold = float(occupy_hold)
        self.release_hold = float(release_hold)
        self._occupied = np.zeros(NUM_ZONES, dtype=bool)
        self._pending_since = np.full(NUM_ZONES, np.nan)
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
        self._occupied[:] = False
        self._pending_since[:] = np.nan

    def update(self, pressure: PressureMap) -> tuple[MatState, list[MatEvent], dict[str, Any]]:
        t = pressure.t
        raw = pressure.values >= self.threshold
        differs = raw != self._occupied

        start = differs & np.isnan(self._pending_since)
        self._pending_since[start] = t
        self._pending_since[~differs] = np.nan

        hold = np.where(self._occupied, self.release_hold, self.occupy_hold)
        commit = differs & (t - self._pending_since >= hold - 1e-9)

        events: list[MatEvent] = []
        for idx in np.flatnonzero(commit):
            kind = "lift" if self._occupied[idx] else "place"
            events.append(MatEvent(kind=kind, zone=int(idx), t=t))
        self._occupied[commit] = ~self._occupied[commit]
        self._pending_since[commit] = np.nan

        counts = np.bincount(_RING_OF[self._occupied], minlength=NUM_RINGS)
        control = None
        if self._control_mask is not None:
            control = float(pressure.values[self._control_mask].sum())
        state = MatState(
            t=t,
            occupied=frozenset(int(i) for i in np.flatnonzero(self._occupied)),
            ring_counts=tuple(int(c) for c in counts),
            control_pressure=control,
        )
        features = {fx.name: fx.compute(pressure, state) for fx in self.extractors}
        return state, events, features
