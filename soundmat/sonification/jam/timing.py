"""时间方案、扫描几何与触发表映射（移植自第一版 ``jam/scheduler/timing.py``）。

| 方案 | 一圈 | 语义 |
|---|---|---|
| 1 | 4 小节 | 1 个扇区 = 1 个八分格 |
| 2 | 2 小节 | 每小节 16 个扇区，相邻 2 个合并为 1 个八分位；每和弦 2 小节；每圈换和弦（默认，系列文档第 8 篇"方案 3"） |
| 3 | 2 小节 | 同 2，但每和弦 1 小节，半圈换和弦 |

扫描位置以扇区为单位：音乐时间 0 时扫描线在第 0 扇区中心（12 点方向），之后按每秒
``steps_per_sec`` 个扇区顺时针前进。扇区编号与外环区域的环内序号一致。
"""
from __future__ import annotations

import math

SECTOR_COUNT = 32
EIGHTHS_PER_BAR = 8
DEFAULT_SCHEME = 2
_DIVISOR = {1: 30.0, 2: 15.0, 3: 15.0}   # steps_per_sec = bpm / divisor


class Timing:
    def __init__(self, scheme: int = DEFAULT_SCHEME):
        if scheme not in _DIVISOR:
            raise ValueError(f"未知的时间方案：{scheme}")
        self.scheme = scheme

    @property
    def is_two_bar(self) -> bool:
        return self.scheme in (2, 3)

    @property
    def bars_per_harmony_cycle(self) -> int:
        return 8 if self.scheme == 2 else 4

    def steps_per_sec(self, bpm: float) -> float:
        return bpm / _DIVISOR[self.scheme]

    def sweep_position(self, musical_time: float, bpm: float) -> float:
        """扫描线累计走过的扇区数（不取模）。"""
        return self.steps_per_sec(bpm) * musical_time

    def trigger_sector(self, sector: int) -> int:
        """两小节方案：相邻 2 个扇区合并为 1 个八分触发位，取偶数扇区。"""
        if not self.is_two_bar:
            return sector
        return sector - (sector % 2)

    def trigger_targets(self) -> range:
        return range(0, SECTOR_COUNT, 2) if self.is_two_bar else range(SECTOR_COUNT)

    def resolve(self, sector: int, loop_rotation: int) -> tuple[int, int]:
        """扇区 → (和弦序号, 小节内八分位)，用于查触发表（4 和弦 × 8 八分）。"""
        s = sector % SECTOR_COUNT
        if self.scheme == 1:
            return s // EIGHTHS_PER_BAR, s % EIGHTHS_PER_BAR
        slice_in_bar = (s % 16) // 2
        bar_global = loop_rotation * 2 + s // 16
        chord = bar_global % 4 if self.scheme == 3 else bar_global // 2
        return chord, slice_in_bar

    def hits_in(self, mt0: float, mt1: float, bpm: float, targets) -> list[tuple[float, int, int]]:
        """音乐时间 [mt0, mt1) 内扫描线经过各目标扇区中心的时刻。

        返回 ``[(音乐时间, 扇区, 第几圈)]``，按时间排序。
        """
        sps = self.steps_per_sec(bpm)
        p0, p1 = sps * mt0, sps * mt1
        out = []
        for target in targets:
            k = math.ceil((p0 - target) / SECTOR_COUNT - 1e-9)
            while True:
                p = k * SECTOR_COUNT + target
                if p >= p1 - 1e-9:
                    break
                if p >= p0 - 1e-9:
                    out.append((p / sps, target, k))
                k += 1
        out.sort()
        return out
