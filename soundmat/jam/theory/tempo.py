"""Tempo：BPM → 时间常数。

所有时间相关参数从 BPM 派生；SC 端只接受绝对秒数，不知道 BPM 存在（设计文档 §5.3）。
拍号固定 4/4，每小节 4 拍、16 个十六分格。
"""
from __future__ import annotations

BEATS_PER_BAR = 4
SIXTEENTHS_PER_BAR = 16
EIGHTHS_PER_BAR = 8


class Tempo:
    def __init__(self, bpm: float = 120.0):
        self.bpm = float(bpm)

    @property
    def sec_per_quarter(self) -> float:
        return 60.0 / self.bpm

    @property
    def sec_per_eighth(self) -> float:
        return 60.0 / self.bpm / 2.0

    @property
    def sec_per_sixteenth(self) -> float:
        return 60.0 / self.bpm / 4.0

    @property
    def sec_per_bar(self) -> float:
        return BEATS_PER_BAR * self.sec_per_quarter

    def sixteenth_ticks(self, prev_time: float, curr_time: float):
        """生成区间 (prev, curr] 内每个新跨过的十六分格：(global_index, step_in_bar, bar_global)。"""
        step = self.sec_per_sixteenth
        prev = int(prev_time // step)
        curr = int(curr_time // step)
        for i in range(prev + 1, curr + 1):
            yield i, i % SIXTEENTHS_PER_BAR, i // SIXTEENTHS_PER_BAR
