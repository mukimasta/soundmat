"""HarmonyEngine：和声 pad 自动循环（设计文档 §6.3 / JAM_DESIGN §4）。

每小节起点（step_in_bar == 0）：先 release 上一和弦，再演奏该小节和弦的 5 音 pad
（含根音），保持 1 小节。和弦序列由 progression 决定，每个和弦的 voicing（5 个级数）
由 chord_voicings 配置给出（首调，随 key 移调）。
"""
from __future__ import annotations

from ..scheduler.song_position import SongPositionTracker
from ..theory.tempo import Tempo
from ..types import ChordEvent


class HarmonyEngine:
    def __init__(
        self,
        song_pos: SongPositionTracker,
        chord_voicings: dict[str, list[str]],
        total_bars: int,
    ):
        self.song_pos = song_pos
        self.chord_voicings = chord_voicings  # symbol -> [degree tokens]（含根音，5 音）
        self.total_bars = total_bars

    def emit(self, prev_time: float, curr_time: float, tempo: Tempo) -> list[ChordEvent]:
        events: list[ChordEvent] = []
        for _global, step_in_bar, bar_global in tempo.sixteenth_ticks(prev_time, curr_time):
            if bar_global >= self.total_bars:
                continue
            if step_in_bar != 0:
                continue
            symbol, _idx, _bar = self.song_pos.harmony_for_bar(bar_global)
            degrees = self.chord_voicings.get(symbol)
            if not degrees:
                continue
            events.append(
                ChordEvent(
                    symbol=symbol,
                    degrees=tuple(degrees),
                    hold=tempo.sec_per_bar,
                    release_first=True,
                )
            )
        return events
