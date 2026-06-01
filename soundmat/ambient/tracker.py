"""Tracker：传感矩阵 → 物体聚类坐标（哪些 (ring,slice) 有石头）。

硬件只能分辨「哪个区域有物」，分不清个数/精确位置；tracker 在此约束下产出稳定 occupied
集合 + 每环计数。这里做最简阈值化（可后续加聚类/防抖）。极性/阈值见 config 标定。
"""
from __future__ import annotations

import numpy as np

from .. import config


class Tracker:
    def __init__(self, threshold: float | None = None, invert: bool | None = None):
        self.threshold = config.SENSOR_THRESHOLD if threshold is None else threshold
        self.invert = config.SENSOR_INVERT if invert is None else invert

    def occupied(self, matrix: np.ndarray) -> set[tuple[int, int]]:
        m = matrix.astype(np.float32)
        m[m < 0] = 0.0
        if self.invert:
            inv = np.clip(config.ADC_MAX - m, 0, config.ADC_MAX)
            inv[matrix < 0] = 0.0
            m = inv
        out: set[tuple[int, int]] = set()
        for ring in range(config.NUM_RINGS):
            n = config.slices_at(ring)
            for slc in range(n):
                if m[ring, slc] >= self.threshold:
                    out.add((ring, slc))
        return out
