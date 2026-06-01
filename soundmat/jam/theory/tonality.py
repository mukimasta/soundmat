"""Tonality：级数 → MIDI / freq（应用 key + scale，首调移调）。

设计文档 §6.3：改 manifest 的 `[music].key` 即完成全局移调，所有级数自动跟着 key 的根音
平移。例：`1^` 在 C 调下是 C5，key 改成 B 后变为 B4——即移到“最近”的根音（B 在 C 下方
一个半音），而不是上方 11 个半音。故 key 偏移取 ±6 内的最近有符号半音距。

整条信号路径上「具体音高」只在这一层那一瞬间存在。
"""
from __future__ import annotations

from .degree import BASE_OCTAVE, DegreeParser, ParsedDegree

# C4 = MIDI 60 = degree 1, octave 4, key C
BASE_MIDI = 60

# 各音阶的级数 → 半音（相对主音）
SCALE_SEMITONES = {
    "major": {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11},
    "natural_minor": {1: 0, 2: 2, 3: 3, 4: 5, 5: 7, 6: 8, 7: 10},
    "harmonic_minor": {1: 0, 2: 2, 3: 3, 4: 5, 5: 7, 6: 8, 7: 11},
    "dorian": {1: 0, 2: 2, 3: 3, 4: 5, 5: 7, 6: 9, 7: 10},
}

# 音名 → 相对 C 的 pitch class（0..11）
_NOTE_PC = {
    "C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "F": 5,
    "F#": 6, "GB": 6, "G": 7, "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11,
}

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def key_offset(key: str) -> int:
    """key 根音相对 C 的“最近有符号半音距”，范围 [-6, +5]。C=0, B=-1, G=-5, F#=-6。"""
    pc = _NOTE_PC.get(key.strip().upper(), 0)
    return ((pc + 6) % 12) - 6


class Tonality:
    def __init__(self, key: str = "C", scale: str = "major"):
        self.key = key
        self.scale = scale
        self._scale_map = SCALE_SEMITONES.get(scale, SCALE_SEMITONES["major"])
        self._key_offset = key_offset(key)
        self._parser = DegreeParser()

    # ── 解析 ──
    def midi(self, token: str | None) -> int | None:
        """级数 token → MIDI 音符号；休止/非法返回 None。"""
        parsed = self._parser.parse(token)
        if parsed is None:
            return None
        return self.midi_of(parsed)

    def midi_of(self, parsed: ParsedDegree) -> int:
        semitone = self._scale_map.get(parsed.degree, 0)
        return (
            BASE_MIDI
            + self._key_offset
            + semitone
            + parsed.accidental
            + (parsed.octave - BASE_OCTAVE) * 12
        )

    def freq(self, token: str | None) -> float | None:
        m = self.midi(token)
        return None if m is None else midi_to_freq(m)

    def freqs(self, tokens) -> list[float]:
        """一组 token → freq 列表（跳过休止）。"""
        out = []
        for t in tokens:
            f = self.freq(t)
            if f is not None:
                out.append(f)
        return out

    @staticmethod
    def note_name(midi: int) -> str:
        return _NOTE_NAMES[midi % 12] + str(midi // 12 - 1)


def midi_to_freq(midi: int) -> float:
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)
