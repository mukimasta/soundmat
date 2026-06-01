"""Ambient LED：氛围提示（简单暖色呼吸 + 已放石位置淡标记）。

ambient 的 LED 偏静态氛围，与 jam 的扫描尾迹不同。本期为简版（暖白呼吸），后续可细化。
"""
from __future__ import annotations

import math

from .. import config

WARM = (255, 180, 90)


def render(now: float, occupied: set[tuple[int, int]] | None = None) -> list[tuple[int, int, int]]:
    breath = 0.25 + 0.2 * (0.5 + 0.5 * math.sin(now * 0.9))
    base = (round(WARM[0] * breath), round(WARM[1] * breath), round(WARM[2] * breath))
    return [base] * config.NUM_LEDS
