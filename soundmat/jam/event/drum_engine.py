"""DrumEngine：鼓自动循环（设计文档 §6.5 / JAM_DESIGN §4）。

每 16 分格按曲式选 A/B/C/D pattern，查 kick/snare/hihat 该格值（0 休止 / 1 正常 / 2 ghost）
发 NoteEvent。曲式 sequence 是「展开」形式：每个条目 = 一个和声循环（barsPerHarmonyCycle
小节），同一 pattern 在该段内逐小节重复。默认 A,B,C,C,A,D,D,A。
"""
from __future__ import annotations

from ..theory.tempo import Tempo
from ..types import NoteEvent

GHOST_VELOCITY = 0.38
DRUM_RING = -1  # 鼓不属于任何感应环；用 -1 标识


class DrumEngine:
    def __init__(
        self,
        patterns: dict[str, dict[str, list[int]]],
        sequence: list[str],
        bars_per_cycle: int,
    ):
        self.patterns = patterns          # {"A": {"kick":[16], "snare":[16], "hihat":[16]}, ...}
        self.sequence = sequence          # 展开序列，每条目 = 一个和声循环
        self.bars_per_cycle = bars_per_cycle
        self.total_bars = len(sequence) * bars_per_cycle

    def loop_for_bar(self, bar_global: int) -> str:
        if not self.sequence:
            return "A"
        cycle_index = (bar_global // self.bars_per_cycle) % len(self.sequence)
        return self.sequence[cycle_index]

    def emit(self, prev_time: float, curr_time: float, tempo: Tempo) -> list[NoteEvent]:
        events: list[NoteEvent] = []
        hat_normal = tempo.sec_per_sixteenth / 2.0   # 32n
        hat_ghost = tempo.sec_per_sixteenth / 4.0     # 64n
        for _global, step_in_bar, bar_global in tempo.sixteenth_ticks(prev_time, curr_time):
            if bar_global >= self.total_bars:
                continue
            pattern = self.patterns.get(self.loop_for_bar(bar_global))
            if not pattern:
                continue
            for voice in ("kick", "snare", "hihat"):
                row = pattern.get(voice)
                if not row or step_in_bar >= len(row):
                    continue
                level = row[step_in_bar]
                if not level:
                    continue
                vel = GHOST_VELOCITY if level == 2 else 1.0
                sustain = tempo.sec_per_eighth
                if voice == "hihat":
                    sustain = hat_ghost if level == 2 else hat_normal
                events.append(
                    NoteEvent(ring=DRUM_RING, voice=voice, velocity=vel, sustain=sustain)
                )
        return events
