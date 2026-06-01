"""数字记谱解析（设计文档 §6.3）。

记号：数字 1–7 = 当前 key 音阶的音级（首调，不绑定固定音高）。
- 升降写在数字后：`#` 升半音，`b` 降半音。
- 八度写在最后：`^` 升一八度，`_` 降一八度，可叠加（`^^` / `__`）。无八度记号 = 第 4 八度。
- 顺序固定：数字 → 升降 → 八度，例如 `1#^`。
- `null` / None = 不发声（由上层处理）。

本模块只把字符串拆成结构化字段，不涉及 key/scale——那是 Tonality 的事。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# 数字 → 升降(可选) → 八度(可选)
_TOKEN_RE = re.compile(r"^([1-7])(#|b)?(\^\^|__|\^|_)?$")

BASE_OCTAVE = 4


@dataclass(frozen=True)
class ParsedDegree:
    degree: int          # 1..7（音级）
    accidental: int      # 半音修正：+1(#) / -1(b) / 0
    octave: int          # 绝对八度（4 = 默认）

    @property
    def octave_offset(self) -> int:
        return self.octave - BASE_OCTAVE


class DegreeParser:
    """无状态解析器。`parse(token)` 返回 ParsedDegree 或 None（空/非法/休止）。"""

    @staticmethod
    def parse(token: str | None) -> ParsedDegree | None:
        if token is None:
            return None
        s = str(token).strip()
        if not s or s.lower() == "null":
            return None
        m = _TOKEN_RE.match(s)
        if not m:
            return None

        degree = int(m.group(1))
        acc = 0
        if m.group(2) == "#":
            acc = 1
        elif m.group(2) == "b":
            acc = -1

        octave = BASE_OCTAVE
        oct_tok = m.group(3)
        if oct_tok == "^":
            octave += 1
        elif oct_tok == "^^":
            octave += 2
        elif oct_tok == "_":
            octave -= 1
        elif oct_tok == "__":
            octave -= 2

        return ParsedDegree(degree=degree, accidental=acc, octave=octave)
