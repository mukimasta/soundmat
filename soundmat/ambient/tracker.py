"""Tracker：传感矩阵 → 逻辑坐标 (ring, sector) 上有石头的集合。"""
from __future__ import annotations

import numpy as np

from .. import config
from ..core.sensor.map import wire_to_logical_adc


class Tracker:
    def __init__(self, threshold: float | None = None, invert: bool | None = None):
        self.threshold = config.SENSOR_THRESHOLD if threshold is None else threshold
        self.invert = config.SENSOR_INVERT if invert is None else invert

    def occupied(self, matrix: np.ndarray) -> set[tuple[int, int]]:
        logical = wire_to_logical_adc(matrix)
        m = logical.astype(np.float32)
        m[m < 0] = 0.0
        if self.invert:
            inv = np.clip(config.ADC_MAX - m, 0, config.ADC_MAX)
            inv[logical < 0] = 0.0
            m = inv
        out: set[tuple[int, int]] = set()
        for ring in range(config.NUM_RINGS):
            for sector in range(config.NUM_SLICES):
                if m[ring, sector] >= self.threshold:
                    out.add((ring, sector))
        return out
