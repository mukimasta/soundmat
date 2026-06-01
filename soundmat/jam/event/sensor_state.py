"""SensorState：传感矩阵 → 石头集合 + 放/拿边沿事件 + R0/R1 控制值。

硬件只能分辨「哪个区域有物」，分不清个数/精确位置。本类在此约束下产出稳定状态：
- 每个 (ring, slice) 单元按压力阈值判定「有/无石头」。
- R0/R1（控制环）：活跃单元的压力之和 → Lo-Fi 控制值（0–1000，设计文档 §6.2 连续实时调控）；
  是否有任意活跃单元 → 开始/停止开关。

ADC 极性可配（real 硬件压力越大 ADC 可能越低，见传感器原理文档），用 `invert` 翻转。
阈值/full_scale 是标定常量，部署时按真实传感器调。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ... import config

CONTROL_RINGS = (0, 1)


@dataclass
class SensorDelta:
    occupied: set[tuple[int, int]]            # 当前所有活跃单元
    placed: list[tuple[int, int]]             # 本帧新增
    removed: list[tuple[int, int]]            # 本帧消失
    control_count: int                        # R0/R1 活跃单元数（粗略石头数）
    control_value: float                      # Lo-Fi 控制值 0..1000
    control_active: bool                      # R0/R1 是否有任意活跃单元


class SensorState:
    def __init__(
        self,
        *,
        threshold: float | None = None,
        invert: bool | None = None,
        control_full_scale: float | None = None,
    ):
        self.threshold = config.SENSOR_THRESHOLD if threshold is None else threshold
        self.invert = config.SENSOR_INVERT if invert is None else invert
        self.control_full_scale = (
            config.CONTROL_FULL_SCALE if control_full_scale is None else control_full_scale
        )
        self._occupied: set[tuple[int, int]] = set()

    def _pressure(self, matrix: np.ndarray) -> np.ndarray:
        m = matrix.astype(np.float32)
        m[m < 0] = 0.0  # -1 无效 → 0
        if self.invert:
            m = np.clip(config.ADC_MAX - m, 0, config.ADC_MAX)
            # 反相后“无效=0”被映射成满值，需重新把原 -1 置 0
            m[matrix < 0] = 0.0
        return m

    def update(self, matrix: np.ndarray) -> SensorDelta:
        pressure = self._pressure(matrix)
        active_mask = pressure >= self.threshold

        occupied: set[tuple[int, int]] = set()
        for ring in range(config.NUM_RINGS):
            n = config.slices_at(ring)
            for slc in range(n):
                if active_mask[ring, slc]:
                    occupied.add((ring, slc))

        placed = sorted(occupied - self._occupied)
        removed = sorted(self._occupied - occupied)
        self._occupied = occupied

        # 控制环
        control_cells = [c for c in occupied if c[0] in CONTROL_RINGS]
        control_count = len(control_cells)
        control_sum = float(sum(pressure[r, s] for r, s in control_cells))
        control_value = min(1000.0, control_sum / self.control_full_scale * 1000.0)

        return SensorDelta(
            occupied=occupied,
            placed=placed,
            removed=removed,
            control_count=control_count,
            control_value=control_value,
            control_active=control_count > 0,
        )

    @property
    def occupied(self) -> set[tuple[int, int]]:
        return set(self._occupied)

    def reset(self) -> None:
        self._occupied = set()
