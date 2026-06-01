"""时间方案 + 扇区/扫描几何 + 扇区→触发表映射（纯函数，移植自 web demo）。

时间方案（设计文档 §6.1 选定「方案 3」= web demo 的 scheme 2 语义）：

| id | 名称   | stepsPerSecond | 一圈      | 和弦/表语义                         |
|----|--------|----------------|-----------|-------------------------------------|
| 1  | 4 bars | bpm/30         | 4 小节    | 1 sector = 1 个八分格              |
| 2  | 2 bars | bpm/15         | 2 小节    | 每小节 16 sector；相邻 2 sector 合并为 1 个八分位；每和弦 2 小节；新和弦每圈 |
| 3  | 2barB  | bpm/15         | 2 小节    | 同 2，但每和弦 1 小节；半圈换和弦  |

**默认 scheme = 2**（与交互文档「方案 3」一致：8 小节进行、每和弦 2 小节、一圈 2 小节、
16 分网格量化到每小节 8 个八分位）。
"""
from __future__ import annotations

import math

SECTOR_COUNT = 32
SECTOR_RADIANS = (2 * math.pi) / SECTOR_COUNT
SWEEP_START_ANGLE = -math.pi / 2  # 12 点钟方向，对齐 sector 0
EIGHTHS_PER_BAR = 8
DEFAULT_SCHEME = 2

_STEPS_PER_SEC = {1: 30.0, 2: 15.0, 3: 15.0}  # bpm / divisor


def normalize_angle(angle: float) -> float:
    return ((angle % (2 * math.pi)) + 2 * math.pi) % (2 * math.pi)


def sector_center_angle(sector: int) -> float:
    """扇区中心角；sector 0 在 12 点钟，索引增大顺时针。"""
    return sector * SECTOR_RADIANS - math.pi / 2


def sweep_crossed_angle(prev: float, curr: float, target: float) -> bool:
    """扫描弧 prev→curr 是否跨过 target 角（均归一化到 [0,2π)）。"""
    p = normalize_angle(prev)
    c = normalize_angle(curr)
    t = normalize_angle(target)
    if c >= p:
        return p <= t < c
    return t >= p or t < c


class Timing:
    """封装某个时间方案的派生量与映射；不持有运行时状态。"""

    def __init__(self, scheme: int = DEFAULT_SCHEME):
        self.scheme = scheme if scheme in _STEPS_PER_SEC else DEFAULT_SCHEME

    @property
    def is_two_bar(self) -> bool:
        return self.scheme in (2, 3)

    @property
    def is_two_bar_b(self) -> bool:
        return self.scheme == 3

    @property
    def bars_per_harmony_cycle(self) -> int:
        return 8 if self.scheme == 2 else 4

    def steps_per_sec(self, bpm: float) -> float:
        return bpm / _STEPS_PER_SEC[self.scheme]

    # ── 扫描角 ──
    def sweep_angle_at(self, musical_time: float, bpm: float) -> float:
        angle = SWEEP_START_ANGLE + SECTOR_RADIANS * self.steps_per_sec(bpm) * musical_time
        wrap = 2 * math.pi
        while angle >= SWEEP_START_ANGLE + wrap:
            angle -= wrap
        return angle

    # ── 扇区合并（两倍量化：相邻 2 物理 sector → 1 个八分触发位）──
    def melody_trigger_sector(self, sector: int, is_trigger_ring: bool) -> int:
        if not self.is_two_bar or not is_trigger_ring:
            return sector
        bar_base = (sector // 16) * 16
        pos_in_bar = sector % 16
        return bar_base + pos_in_bar - (pos_in_bar % 2)

    # ── 扇区 → 32 格触发表（4 和弦 × 8 八分）──
    def map_to_table_sector(self, sector: int, loop_rotation: int) -> int:
        s = ((sector % SECTOR_COUNT) + SECTOR_COUNT) % SECTOR_COUNT
        if self.scheme == 1:
            return s
        pos_in_bar = s % 16
        slice_in_bar = pos_in_bar // 2
        bar_in_rotation = s // 16
        if self.is_two_bar_b:
            bar_global = loop_rotation * 2 + bar_in_rotation
            chord_index = bar_global % 4
            return chord_index * 8 + slice_in_bar
        bar_global = loop_rotation * 2 + bar_in_rotation
        table_bar = bar_global // 2
        return table_bar * 8 + slice_in_bar

    def resolve_position(self, sector: int, loop_rotation: int) -> dict:
        """sector → {table_sector, chord_index, eighth_in_bar}。"""
        table_sector = self.map_to_table_sector(sector, loop_rotation)
        chord_index = table_sector // EIGHTHS_PER_BAR
        eighth_in_bar = table_sector % EIGHTHS_PER_BAR
        return {
            "table_sector": table_sector,
            "chord_index": chord_index,
            "eighth_in_bar": eighth_in_bar,
        }

    def effective_loop_rotation(self, sector: int, loop_rotation: int, did_wrap: bool) -> int:
        """回绕帧上区分 sector 0-15（新进半圈）与 16-31（仍在出半圈）。"""
        if not self.is_two_bar or not did_wrap:
            return loop_rotation
        return loop_rotation if sector >= 16 else (loop_rotation + 1) % 4
