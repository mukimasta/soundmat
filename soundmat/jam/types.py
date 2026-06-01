"""Jam 各层之间流动的事件对象（契约文件，设计文档 §5.5 / §12.3）。

单独提出来避免循环依赖，也让上下游契约一目了然：scheduler 产生什么形状的 tick、
event 产生什么形状的 NoteEvent、bridge 期望接收什么——大家通过这个文件达成一致。

记号约定：`degree` 是字符串形式的级数（如 "1#^"），**未解析为 MIDI**。
具体音高只在桥层那一瞬间存在（bridge 调 Tonality 翻译成 freq）。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NoteEvent:
    """量化触发的音符事件（旋律 / bass / 鼓）。"""

    ring: int
    degree: str | None = None   # 旋律/bass：级数字符串；鼓：None
    voice: str | None = None    # 鼓声部 "kick"/"snare"/"hihat"；旋律/bass：None
    velocity: float = 1.0       # 0..1
    sustain: float = 0.5        # 已换算成秒
    pan: float = 0.0
    when: float = 0.0           # 相对“现在”的延时（秒），保留给未来错开用
    source_slice: int | None = None  # 触发它的物理扇区（LED 命中闪用，桥层忽略）

    @property
    def is_drum(self) -> bool:
        return self.voice is not None


@dataclass(frozen=True)
class ChordEvent:
    """和声 pad 触发：一次 5 音和弦，保持 hold 秒。先 release 上一和弦。"""

    symbol: str                 # 和弦符号，如 "2m9"
    degrees: tuple[str, ...]    # 5 个级数（含根音），或直接给频率见 freqs
    hold: float                 # 保持时长（秒），= 1 小节
    release_first: bool = True


@dataclass(frozen=True)
class ParamEvent:
    """连续参数变化（如 Lo-Fi 强度）。"""

    param: str                  # "lofi_amount"
    value: float


@dataclass(frozen=True)
class SliceTick:
    """扫描线推进事件。"""

    slice: int                  # 0..31（物理扇区）
    timestamp: float            # 主时钟绝对时刻
    did_wrap: bool = False      # 本帧是否整圈回绕


@dataclass(frozen=True)
class SongPosition:
    """当前歌曲位置。"""

    chord_idx: int              # 在 progression 里的索引
    bar: int                    # 当前是和弦内的第几小节（0 或 1）
    sub_loop: int               # 整曲循环到第几遍（这里指全局 bar 索引推导的 loop_rotation）
    bar_global: int = 0         # 全局小节索引（从开拍起算）
