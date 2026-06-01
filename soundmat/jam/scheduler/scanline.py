"""ScanLine：musical_time → 扫描角，并跟踪 prev→curr 用于命中检测。

扫描角完全由主时钟派生（不独立累积 dt），保证扫描与伴奏不漂移。每帧给出
(prev_angle, curr_angle, did_wrap)，事件层据此判断哪些石头被扫中。
"""
from __future__ import annotations

import math

from .timing import (
    SECTOR_COUNT,
    SECTOR_RADIANS,
    SWEEP_START_ANGLE,
    Timing,
    normalize_angle,
)


class ScanLine:
    def __init__(self, timing: Timing):
        self.timing = timing
        self.prev_angle = SWEEP_START_ANGLE
        self.curr_angle = SWEEP_START_ANGLE
        # 扫线回绕计数（web demo loopRotationRef）；触发表映射用，与 bar_global 解耦
        self.loop_rotation = 0

    def reset(self) -> None:
        self.prev_angle = SWEEP_START_ANGLE
        self.curr_angle = SWEEP_START_ANGLE
        self.loop_rotation = 0

    def set_timing(self, timing: Timing) -> None:
        self.timing = timing

    def update(self, musical_time: float, bpm: float) -> tuple[float, float, bool]:
        self.prev_angle = self.curr_angle
        self.curr_angle = self.timing.sweep_angle_at(musical_time, bpm)
        did_wrap = self.curr_angle < self.prev_angle and self.timing.is_two_bar
        return self.prev_angle, self.curr_angle, did_wrap

    @property
    def current_sector(self) -> int:
        return self.sector_at(self.curr_angle)

    @staticmethod
    def sector_at(angle: float) -> int:
        normalized = normalize_angle(angle + math.pi / 2)
        sector = int((normalized + SECTOR_RADIANS / 2) // SECTOR_RADIANS)
        if sector >= SECTOR_COUNT:
            sector = 0
        return sector
