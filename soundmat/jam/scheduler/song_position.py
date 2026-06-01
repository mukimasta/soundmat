"""SongPosition：musical_time → 当前 chord / bar / loop_rotation + 和声查询。

进行（progression）是数据驱动的：[(chord_id, bars), ...]。和声 pad 与触发表都按它对齐。
设计默认进行 1 = 2m9 → 513 → 1maj9 → 69（4 和弦，scheme 2 下每和弦 2 小节 = 8 小节循环）。
"""
from __future__ import annotations

from ..theory.tempo import BEATS_PER_BAR
from ..types import SongPosition
from .timing import Timing


class SongPositionTracker:
    def __init__(self, progression: list[tuple[str, int]], timing: Timing):
        self.progression = progression          # [(id, bars), ...]
        self.timing = timing
        self.cycle_bars = sum(bars for _, bars in progression) or 1
        # 预展开：bar_in_cycle → chord_index
        self._bar_to_chord: list[int] = []
        for idx, (_, bars) in enumerate(progression):
            self._bar_to_chord.extend([idx] * bars)

    def set_timing(self, timing: Timing) -> None:
        self.timing = timing

    def bar_global(self, musical_time: float, bpm: float) -> int:
        sec_per_bar = BEATS_PER_BAR * (60.0 / bpm)
        return int(musical_time // sec_per_bar)

    def harmony_for_bar(self, bar_global: int) -> tuple[str, int, int]:
        """返回 (chord_symbol, chord_index, bar_in_chord_0based)。"""
        bar_in_cycle = bar_global % self.cycle_bars
        chord_index = self._bar_to_chord[bar_in_cycle]
        # 该和弦内的第几小节
        start = sum(b for _, b in self.progression[:chord_index])
        bar_in_chord = bar_in_cycle - start
        return self.progression[chord_index][0], chord_index, bar_in_chord

    def loop_rotation(self, bar_global: int) -> int:
        """触发表用的循环旋转量。两小节方案：每 2 小节 +1，循环 0..3。四小节方案：恒 0。"""
        if not self.timing.is_two_bar:
            return 0
        return (bar_global // 2) % 4

    def position_at(self, musical_time: float, bpm: float) -> SongPosition:
        bg = self.bar_global(musical_time, bpm)
        _, chord_index, bar_in_chord = self.harmony_for_bar(bg)
        return SongPosition(
            chord_idx=chord_index,
            bar=bar_in_chord,
            sub_loop=self.loop_rotation(bg),
            bar_global=bg,
        )
