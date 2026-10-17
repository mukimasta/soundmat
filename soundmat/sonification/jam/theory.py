"""Jam 的音乐理论：数字记谱、调与音阶、速度（移植自第一版 ``jam/theory``）。

记号：数字 1–7 = 当前调音阶的音级（首调）。升降写在数字后（``#`` 升、``b`` 降），八度写在最后
（``^`` 升一八度、``_`` 降一八度，可叠加为 ``^^`` / ``__``）；无八度记号 = 第 4 八度。
例如 ``1#^``。``None`` / ``"null"`` / 空 = 不发声。

具体音高只在 ``Tonality`` 这一层出现。改调时所有级数跟着主音平移到"最近"的根音：
例如 ``1^`` 在 C 调是 C5，改成 B 调后是 B4（B 在 C 下方一个半音），而不是上方 11 个半音。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

BASE_OCTAVE = 4
BASE_MIDI = 60          # C4 = 1 级、第 4 八度、C 调
BEATS_PER_BAR = 4
SIXTEENTHS_PER_BAR = 16

_TOKEN_RE = re.compile(r"^([1-7])(#|b)?(\^\^|__|\^|_)?$")

SCALE_SEMITONES = {
    "major": {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11},
    "natural_minor": {1: 0, 2: 2, 3: 3, 4: 5, 5: 7, 6: 8, 7: 10},
    "harmonic_minor": {1: 0, 2: 2, 3: 3, 4: 5, 5: 7, 6: 8, 7: 11},
    "dorian": {1: 0, 2: 2, 3: 3, 4: 5, 5: 7, 6: 9, 7: 10},
}

_NOTE_PC = {
    "C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "F": 5,
    "F#": 6, "GB": 6, "G": 7, "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11,
}

_OCTAVE = {None: 0, "^": 1, "^^": 2, "_": -1, "__": -2}


@dataclass(frozen=True)
class ParsedDegree:
    degree: int          # 1..7
    accidental: int      # +1 / -1 / 0
    octave: int          # 绝对八度（4 = 默认）


def parse_degree(token: str | None) -> ParsedDegree | None:
    """解析一个级数记号；休止或非法记号返回 None。"""
    if token is None:
        return None
    s = str(token).strip()
    if not s or s.lower() == "null":
        return None
    m = _TOKEN_RE.match(s)
    if not m:
        return None
    acc = {"#": 1, "b": -1}.get(m.group(2) or "", 0)
    return ParsedDegree(int(m.group(1)), acc, BASE_OCTAVE + _OCTAVE[m.group(3)])


def valid_token(token) -> bool:
    return token is None or str(token).strip().lower() in ("", "null") or parse_degree(token) is not None


def key_offset(key: str) -> int:
    """主音相对 C 的最近有符号半音距，范围 [-6, +5]。"""
    pc = _NOTE_PC.get(key.strip().upper())
    if pc is None:
        raise ValueError(f"未知的调：{key}")
    return ((pc + 6) % 12) - 6


def midi_to_freq(midi: float) -> float:
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


class Tonality:
    def __init__(self, key: str = "C", scale: str = "major"):
        if scale not in SCALE_SEMITONES:
            raise ValueError(f"未知的音阶：{scale}")
        self.key, self.scale = key, scale
        self._map = SCALE_SEMITONES[scale]
        self._offset = key_offset(key)

    def midi(self, token: str | None) -> int | None:
        p = parse_degree(token)
        if p is None:
            return None
        return BASE_MIDI + self._offset + self._map[p.degree] + p.accidental + (p.octave - BASE_OCTAVE) * 12

    def freq(self, token: str | None) -> float | None:
        m = self.midi(token)
        return None if m is None else midi_to_freq(m)

    def freqs(self, tokens) -> list[float]:
        return [f for f in (self.freq(t) for t in tokens) if f is not None]


@dataclass(frozen=True)
class Tempo:
    """拍号固定 4/4。所有时间从 BPM 派生。"""
    bpm: float

    @property
    def quarter(self) -> float:
        return 60.0 / self.bpm

    @property
    def eighth(self) -> float:
        return self.quarter / 2

    @property
    def sixteenth(self) -> float:
        return self.quarter / 4

    @property
    def bar(self) -> float:
        return BEATS_PER_BAR * self.quarter

    def sixteenths_in(self, t0: float, t1: float) -> range:
        """音乐时间区间 [t0, t1) 内落下的十六分格序号（全局，从 0 开始）。"""
        import math
        first = max(0, math.ceil(t0 / self.sixteenth - 1e-9))
        last = math.ceil(t1 / self.sixteenth - 1e-9)
        return range(first, max(first, last))
