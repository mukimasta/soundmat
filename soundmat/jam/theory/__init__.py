"""音乐理论层（静态服务，纯函数）：

- DegreeParser：解析数字记谱 "1#^" → (degree, accidental, octave)
- Tonality：级数 → MIDI / freq（应用 key + scale，首调移调）
- Tempo：BPM → 时间常数
"""

from .degree import DegreeParser, ParsedDegree
from .tonality import Tonality
from .tempo import Tempo

__all__ = ["DegreeParser", "ParsedDegree", "Tonality", "Tempo"]
