"""调度层（节拍器）：

- timing：扇区/扫描几何 + 时间方案常量 + 扇区→表映射（纯函数）
- Transport：启停 + 主时钟（musical_time）+ 曲终判定
- ScanLine：musical_time → 扫描角 → 当前/跨越的扇区
- SongPosition：musical_time → 当前 chord / bar / loop_rotation + 和声查询
"""

from .timing import Timing, DEFAULT_SCHEME, SECTOR_COUNT
from .transport import Transport
from .scanline import ScanLine
from .song_position import SongPositionTracker

__all__ = [
    "Timing",
    "DEFAULT_SCHEME",
    "SECTOR_COUNT",
    "Transport",
    "ScanLine",
    "SongPositionTracker",
]
