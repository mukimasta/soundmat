"""意图：声音化每拍交出的完整描述，也是声音化与声音引擎、灯光引擎、录制之间的约定（DATA_MODEL「声音意图」「灯光意图」「模式状态」）。

意图是声明式的：持续声部描述"此刻应该存在哪些声音"，声音引擎拿它和实际在响的声音对账；
定时事件是时间窗内要发生的单次声音，每个只交出一次。

时刻只分两种：给出时刻（事件的 ``time``、声部的 ``start``）表示"要在这一刻准时响"，用于有节奏的
声音；不给（None）表示"立即"，用于对动作的反应，例如放下石头时的预听。准时靠声音引擎统一的提前量
保证（``sound.schedule_ahead``），听到的时刻比给出的时刻晚这么多，模式画灯光时据此对齐（``ModeContext``）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping

import numpy as np


@dataclass(frozen=True)
class Position:
    """垫面上的位置：角度（度，12 点方向为 0，顺时针）和归一化半径（0 圆心，1 外缘）。"""
    angle: float
    radius: float


@dataclass(frozen=True)
class Source:
    """声源：一个音色（合成器服务里的 SynthDef）或一段声音素材（素材库内的相对路径）。"""
    kind: Literal["instrument", "sample"]
    name: str


@dataclass(frozen=True)
class Voice:
    """持续声部。``id`` 由模式指定，同一个声音在相邻两拍保持相同标识。"""
    id: str
    source: Source
    bus: str                                  # 汇入的总线：环（"ring3"）或模式声明的分组（"harmony"）
    params: Mapping[str, float] = field(default_factory=dict)
    fade_in: float = 0.05
    fade_out: float = 0.5
    position: Position | None = None          # None = 不定位，充满整个空间
    priority: int = 0
    category: str | None = None               # 声部预算的类别，例如 "melodic"
    start: float | None = None                # 有确定开始时刻时给出（系统时间），例如下一小节的和声；None = 立即开始


@dataclass(frozen=True)
class Event:
    """定时事件：在准确时刻发生的单次声音。``id`` 全局唯一，引擎按它去重。"""
    id: str
    time: float | None                        # 有确定时刻时给出（系统时间），例如鼓点、扫描命中；None = 立即（例如预听）
    source: Source
    bus: str
    params: Mapping[str, float] = field(default_factory=dict)
    position: Position | None = None
    priority: int = 0
    category: str | None = None


@dataclass(frozen=True)
class SoundIntent:
    voices: tuple[Voice, ...] = ()
    events: tuple[Event, ...] = ()
    globals: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class LightLayer:
    """一层灯光：每个逻辑位置一个颜色（0–1 的 RGB）和不透明度。"""
    name: str
    priority: int
    rgb: np.ndarray                           # shape (led_count, 3)
    alpha: np.ndarray                         # shape (led_count,)

    @staticmethod
    def blank(name: str, priority: int, led_count: int) -> "LightLayer":
        return LightLayer(name, priority, np.zeros((led_count, 3), dtype=np.float32),
                          np.zeros(led_count, dtype=np.float32))


@dataclass(frozen=True)
class LightIntent:
    layers: tuple[LightLayer, ...] = ()


@dataclass(frozen=True)
class ModeStatus:
    """给控制台看的模式状态（DATA_MODEL「模式状态」）。"""
    text: str = ""
    reading: str | None = None                # 一个数值读数，例如 "Lo-Fi 45%"
    transport: str | None = None              # 走带状态，例如 "idle" / "playing" / "ended"

    def to_json(self) -> dict:
        return {"text": self.text, "reading": self.reading, "transport": self.transport}


@dataclass(frozen=True)
class BeatOutput:
    sound: SoundIntent = field(default_factory=SoundIntent)
    light: LightIntent = field(default_factory=LightIntent)
    status: ModeStatus = field(default_factory=ModeStatus)
