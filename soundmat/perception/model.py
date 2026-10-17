"""感知的标准输出（DATA_MODEL「压力图」「垫面状态」「垫面事件」「特征」）。

声音化、控制台和录制都只依赖这里的数据，不读取原始帧。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from .zones import NUM_RINGS, NUM_ZONES


@dataclass(frozen=True)
class PressureMap:
    """垫面信号（或虚拟垫子）的输出：每个区域一个 0–1 的归一化压力。"""
    t: float                      # 产生时刻（系统时间）
    seq: int                      # 来源帧序号
    values: np.ndarray            # shape (224,), float32

    def __post_init__(self):
        if self.values.shape != (NUM_ZONES,):
            raise ValueError(f"压力图应有 {NUM_ZONES} 个值，实际 {self.values.shape}")


@dataclass(frozen=True)
class MatEvent:
    kind: Literal["place", "lift"]
    zone: int                     # 区域全局序号
    t: float


@dataclass(frozen=True)
class MatState:
    t: float
    occupied: frozenset[int]      # 被判断为有石头的区域
    ring_counts: tuple[int, ...]  # 每环被占用的区域数
    control_pressure: float | None  # 控制区压力总和；没有声明控制区时为 None


@dataclass(frozen=True)
class MatSnapshot:
    """最新值：压力图 + 垫面状态 + 特征。"""
    pressure: PressureMap
    state: MatState
    features: dict[str, Any] = field(default_factory=dict)
    source: Literal["controller", "virtual"] = "controller"

    @property
    def t(self) -> float:
        return self.state.t


def empty_snapshot(t: float = 0.0, source: Literal["controller", "virtual"] = "controller") -> MatSnapshot:
    return MatSnapshot(
        pressure=PressureMap(t=t, seq=0, values=np.zeros(NUM_ZONES, dtype=np.float32)),
        state=MatState(t=t, occupied=frozenset(), ring_counts=(0,) * NUM_RINGS, control_pressure=None),
        source=source,
    )
