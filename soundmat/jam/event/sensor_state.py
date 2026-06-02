"""SensorState：Wire 矩阵经 S→L 映射后，在 (ring, sector) 逻辑坐标上阈值化。"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ... import config
from ...core.sensor.map import wire_to_logical_adc

CONTROL_RINGS = (0, 1)


@dataclass
class SensorDelta:
    occupied: set[tuple[int, int]]            # 当前所有活跃单元
    placed: list[tuple[int, int]]             # 本帧新增
    removed: list[tuple[int, int]]            # 本帧消失
    control_count: int                        # R0/R1 活跃单元数（粗略石头数）
    control_value: float                      # Lo-Fi 控制值 0..1000
    control_sum: float                        # R0/R1 压力之和（原始 ADC）
    control_active: bool                      # control_sum ≥ control_sum_min


class SensorState:
    def __init__(
        self,
        *,
        threshold: float | None = None,
        invert: bool | None = None,
        control_min: float | None = None,
        control_max: float | None = None,
        control_sum_min: float | None = None,
    ):
        self.threshold = config.SENSOR_THRESHOLD if threshold is None else threshold
        self.invert = config.SENSOR_INVERT if invert is None else invert
        self.control_min = config.CONTROL_MIN if control_min is None else control_min
        self.control_max = config.CONTROL_MAX if control_max is None else control_max
        self.control_sum_min = config.CONTROL_SUM_MIN if control_sum_min is None else control_sum_min
        self._occupied: set[tuple[int, int]] = set()

    def _control_value_from_sum(self, control_sum: float) -> float:
        lo, hi = self.control_min, self.control_max
        if hi <= lo:
            return 1000.0 if control_sum >= hi else 0.0
        t = (control_sum - lo) / (hi - lo)
        return max(0.0, min(1000.0, t * 1000.0))

    def _pressure(self, matrix: np.ndarray) -> np.ndarray:
        m = matrix.astype(np.float32)
        m[m < 0] = 0.0  # -1 无效 → 0
        if self.invert:
            m = np.clip(config.ADC_MAX - m, 0, config.ADC_MAX)
            # 反相后“无效=0”被映射成满值，需重新把原 -1 置 0
            m[matrix < 0] = 0.0
        return m

    def update(self, matrix: np.ndarray) -> SensorDelta:
        logical = wire_to_logical_adc(matrix)
        pressure = self._pressure(logical)
        active_mask = pressure >= self.threshold

        occupied: set[tuple[int, int]] = set()
        for ring in range(config.NUM_RINGS):
            for sector in range(config.NUM_SLICES):
                if active_mask[ring, sector]:
                    occupied.add((ring, sector))

        placed = sorted(occupied - self._occupied)
        removed = sorted(self._occupied - occupied)
        self._occupied = occupied

        # 控制环：Lo-Fi / active 用 R0+R1 全格压力之和；count 仍用超阈值格数
        control_sum = float(pressure[CONTROL_RINGS, :].sum())
        control_cells = [c for c in occupied if c[0] in CONTROL_RINGS]
        control_count = len(control_cells)
        control_value = self._control_value_from_sum(control_sum)

        return SensorDelta(
            occupied=occupied,
            placed=placed,
            removed=removed,
            control_count=control_count,
            control_value=control_value,
            control_sum=control_sum,
            control_active=control_sum >= self.control_sum_min,
        )

    @property
    def occupied(self) -> set[tuple[int, int]]:
        return set(self._occupied)

    def reset(self) -> None:
        self._occupied = set()
