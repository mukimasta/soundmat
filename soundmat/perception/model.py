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
    """放下、拿起、挪动以一颗石头为单位；静下来是整张垫子一段时间没有这三种事件。"""
    kind: Literal["place", "lift", "move", "settle"]
    zone: int | None              # 石头的主区（挪动是挪到的区）；静下来没有区
    t: float
    stone: int | None = None      # 石头标识，同一颗石头从放下到拿起不变
    from_zone: int | None = None  # 挪动：从哪个区挪过来


@dataclass(frozen=True)
class MatState:
    t: float
    occupied: frozenset[int]      # 每颗石头的主区（一颗石头只算一个区，即使它压到了几个区）
    ring_counts: tuple[int, ...]  # 每环的石头数（按主区）
    control_pressure: float | None  # 控制区压力总和；没有声明控制区时为 None
    stones: tuple[Any, ...] = ()  # 垫面上的石头（``interpret.stones.Stone``）


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
