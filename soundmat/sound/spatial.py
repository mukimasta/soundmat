"""空间化：垫面位置 → 各只音箱的增益（SOUND_ENGINE「空间化」）。

音箱布局是一组音箱的水平方位（度，房间里的方向，顺时针）。垫面角度加上朝向偏移得到房间方位。
立体声预设把两只音箱放在 270°、90°（垫面的 9 点、3 点）：垫面左半边偏左、右半边偏右，3 点和 9 点
完全在一侧，12 点和 6 点在正中，左右对称地用满。

分配公式：
1. 方向：在房间方位两侧相邻的两只音箱之间做等功率分配（只有一只音箱时全给它）。
2. 半径：``g = r · g_方向 + (1 − r) · g_均匀``，越靠近圆心越均匀地分布到所有音箱；
   最后整体归一到等功率（各增益平方和为 1），使位置变化不改变响度。
3. 不定位的声音均匀分布：每只音箱 1/√N。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..intent import Position


@dataclass(frozen=True)
class SpeakerLayout:
    azimuths: tuple[float, ...]       # 每只音箱的方位（度）
    names: tuple[str, ...] = ()

    @property
    def channels(self) -> int:
        return len(self.azimuths)

    @staticmethod
    def preset(kind: str) -> "SpeakerLayout":
        return PRESETS[kind]

    def to_json(self) -> dict:
        return {"azimuths": list(self.azimuths), "names": list(self.names)}

    @staticmethod
    def from_json(d: dict) -> "SpeakerLayout":
        az = tuple(float(a) for a in d["azimuths"])
        if not az:
            raise ValueError("音箱布局至少要有一只音箱")
        return SpeakerLayout(az, tuple(d.get("names") or ()))


PRESETS = {
    "stereo": SpeakerLayout((270.0, 90.0), ("左", "右")),
    "quad": SpeakerLayout((315.0, 45.0, 135.0, 225.0), ("左前", "右前", "右后", "左后")),
    "octo": SpeakerLayout(tuple(i * 45.0 for i in range(8)), tuple(f"{i + 1}" for i in range(8))),
}


def uniform_gains(n: int) -> list[float]:
    return [1.0 / math.sqrt(n)] * n


def _directional(room_deg: float, az: tuple[float, ...]) -> list[float]:
    n = len(az)
    if n == 1:
        return [1.0]
    order = sorted(range(n), key=lambda i: az[i] % 360)
    angles = [az[i] % 360 for i in order]
    a = room_deg % 360
    gains = [0.0] * n
    for k in range(n):
        lo, hi = angles[k], angles[(k + 1) % n]
        width = (hi - lo) % 360 or 360.0
        off = (a - lo) % 360
        if off <= width:
            frac = off / width
            gains[order[k]] = math.cos(frac * math.pi / 2)
            gains[order[(k + 1) % n]] = math.sin(frac * math.pi / 2)
            return gains
    return gains  # 不会到达


def speaker_gains(position: Position | None, layout: SpeakerLayout, orientation: float = 0.0) -> list[float]:
    n = layout.channels
    if position is None:
        return uniform_gains(n)
    r = min(1.0, max(0.0, position.radius))
    d = _directional(position.angle + orientation, layout.azimuths)
    u = uniform_gains(n)
    g = [r * di + (1 - r) * ui for di, ui in zip(d, u)]
    power = math.sqrt(sum(x * x for x in g)) or 1.0
    return [x / power for x in g]


@dataclass(frozen=True)
class SpeakerGains:
    """一个声部的音箱增益：单声道声源用 ``mono``；立体声声源的左右声道分别用 ``left``、``right``。"""
    mono: list[float]
    left: list[float]
    right: list[float]


STEREO_SPREAD = 10.0     # 定位的立体声声源：左右声道各偏开的角度（度）
STEREO_FRONT = (330.0, 30.0)    # 不定位的立体声声源在多只音箱时的左右声道方位（左前、右前）


def voice_gains(position: Position | None, layout: SpeakerLayout, orientation: float = 0.0) -> SpeakerGains:
    """立体声声源（例如环境录音、带合唱效果的音色）：

    - 不定位时左右声道放在房间的左前（330°）和右前（30°）；只有两只音箱时直接放在两只音箱上，
      就是原样的左右声道；
    - 定位时左右声道放在位置两侧各 10°，保留一点宽度。
    """
    mono = speaker_gains(position, layout, orientation)
    if position is None:
        if layout.channels == 2:      # 偏左（方位的正弦更小）的那只是左
            lo, hi = sorted(layout.azimuths, key=lambda a: math.sin(math.radians(a)))
        else:
            lo, hi = STEREO_FRONT
        left = speaker_gains(Position(lo, 1.0), layout, 0.0)
        right = speaker_gains(Position(hi, 1.0), layout, 0.0)
    else:
        left = speaker_gains(Position(position.angle - STEREO_SPREAD, position.radius), layout, orientation)
        right = speaker_gains(Position(position.angle + STEREO_SPREAD, position.radius), layout, orientation)
    return SpeakerGains(mono, left, right)
