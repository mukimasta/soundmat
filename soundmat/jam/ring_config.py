"""RingConfig：单环角色 + 音色 + 触发参数（来自 rings.yaml）。

被 event_engine（判定触发环、取 note_sec）与 bridge（取 instrument/gain/额外参数）共用。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RingConfig:
    ring: int
    role: str                       # control / bass / melody / none
    instrument: str | None = None   # SC SynthDef 名（melody/bass 环）
    note_sec: float = 0.5           # 旋律环触发音 gate 时长（秒）
    tail_sec: float = 0.0           # bass 环尾音（web bassTailSec）：实际 gate = 四分音符 + tail
    gain: float = 1.0               # 该环 makeup 增益（线性），桥层乘进 amp
    params: dict = field(default_factory=dict)  # 额外 synth 参数（如 rhodes far=1）

    @property
    def is_trigger(self) -> bool:
        return self.role in ("melody", "bass")

    @property
    def is_control(self) -> bool:
        return self.role == "control"
