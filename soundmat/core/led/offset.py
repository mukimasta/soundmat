"""逻辑 LED 环 → 物理灯带编号：合成后在 offset=0 坐标系，发硬件前统一旋转。"""
from __future__ import annotations

from ... import config

RGB = tuple[int, int, int]


def apply_led_offset(buf: list[RGB], offset: int | None = None) -> list[RGB]:
    """逻辑 index k 的颜色写到物理 LED (k + offset) % NUM_LEDS。"""
    n = config.NUM_LEDS
    off = int(config.LED_OFFSET if offset is None else offset) % n
    if off == 0:
        return list(buf)
    src = list(buf)
    if len(src) < n:
        src += [(0, 0, 0)] * (n - len(src))
    return [src[(i - off) % n] for i in range(n)]
