"""LED 调色板 + 几何 + 包络（移植自 web demo ledRing.js / ringColors.js）。

颜色用 RGB 0–255 + opacity（合成时折叠进 RGB）。时间一律用秒。
"""
from __future__ import annotations

import math

from ... import config

LED_COUNT = config.NUM_LEDS  # 108
SECTOR_COUNT = 32
LED_ANGLE = (2 * math.pi) / LED_COUNT

CARDINAL_LED_INDICES = (0, 27, 54, 81)  # 北/东/南/西卡位

WHITE = (255, 255, 255)
RED_FULL = (255, 48, 48)
RED_MUTED = (255, 140, 140)

# 各环 LED 色（interaction 文档 §6.6 / ringColors.js）
RING_LED_RGB = {
    0: (100, 108, 128),
    1: (148, 112, 88),
    2: (88, 72, 210),
    3: (32, 188, 148),
    4: (48, 152, 255),
    5: (200, 72, 168),
    6: (218, 158, 48),
    7: (255, 108, 32),
}

# 扫描尾迹：相对扫描头落后 0..10 颗的亮度比例
SWEEP_OPACITY_BY_DIST = [1.0, 0.75, 0.40, 0.30, 0.22, 0.15, 0.10, 0.06, 0.03, 0.01, 0.0]
SWEEP_TRAIL_WIDTH = 10

# 扫描命中：偏移 +1/0/−1/−2（无 +2），按 |offset| 衰减
SCAN_HIT_OFFSETS = {0, 1, -1, -2}
SCAN_HIT_FALLOFF = [1.0, 0.82, 0.52]
SCAN_HIT_DURATION = 0.18
SCAN_ATTACK = 0.01
SCAN_HOLD = 0.05

PREVIEW_DURATION = 1.0
CARDINAL_BREATH_MIN = 0.5


def ring_led_rgb(ring: int) -> tuple[int, int, int]:
    return RING_LED_RGB.get(ring, WHITE)


def led_index_for_sector(sector: int) -> int:
    n = ((sector % SECTOR_COUNT) + SECTOR_COUNT) % SECTOR_COUNT
    return round(n / SECTOR_COUNT * LED_COUNT) % LED_COUNT


def normalize_angle(a: float) -> float:
    return ((a % (2 * math.pi)) + 2 * math.pi) % (2 * math.pi)


def led_index_for_angle(angle: float) -> int:
    normalized = normalize_angle(angle + math.pi / 2)
    idx = round(normalized / LED_ANGLE) % LED_COUNT
    return idx


def led_indices_for_sector_span(sector: int, span: int = 2) -> list[int]:
    center = led_index_for_sector(sector)
    return [(center + d + LED_COUNT) % LED_COUNT for d in range(-span, span + 1)]


def led_signed_offset(led_index: int, center: int) -> int:
    d = (led_index - center + LED_COUNT) % LED_COUNT
    if d > LED_COUNT // 2:
        d -= LED_COUNT
    return d


def led_distance_behind(led_index: int, sweep_led: int) -> int | None:
    """扫描头后方的步数；前方返回 None（不亮）。"""
    behind = (sweep_led - led_index + LED_COUNT) % LED_COUNT
    if behind > LED_COUNT // 2:
        return None
    return behind


def wrap_led_distance(a: int, b: int) -> int:
    d = abs(a - b)
    return min(d, LED_COUNT - d)


def breath_phase(t: float) -> float:
    return 0.5 + 0.5 * math.sin(t * 1.35)


def pulse_mix(elapsed: float, duration: float = PREVIEW_DURATION) -> float:
    """预览余弦淡出。"""
    if elapsed <= 0:
        return 1.0
    if elapsed >= duration:
        return 0.0
    return 0.5 * (1 + math.cos(math.pi * elapsed / duration))


def scan_hit_mix(elapsed: float) -> float:
    """命中包络：attack → hold → 平方衰减。"""
    if elapsed < 0:
        return 0.0
    if elapsed <= SCAN_HOLD:
        return 1.0
    if elapsed >= SCAN_HIT_DURATION:
        return 0.0
    t = (elapsed - SCAN_HOLD) / (SCAN_HIT_DURATION - SCAN_HOLD)
    return 1.0 - t * t


# ── RGBA 工具 ──
def rgba(rgb: tuple[int, int, int], opacity: float) -> tuple[int, int, int, float]:
    return (rgb[0], rgb[1], rgb[2], max(0.0, min(1.0, opacity)))


def luminance(c) -> float:
    return (c[0] * 0.299 + c[1] * 0.587 + c[2] * 0.114) * c[3]


def max_state(a, b):
    return b if luminance(b) >= luminance(a) else a


def blend_over(base, overlay, mix: float):
    m = max(0.0, min(1.0, mix))
    if m <= 0:
        return base
    return (
        round(base[0] * (1 - m) + overlay[0] * m),
        round(base[1] * (1 - m) + overlay[1] * m),
        round(base[2] * (1 - m) + overlay[2] * m),
        min(1.0, base[3] * (1 - m) + overlay[3] * m),
    )


def flatten(c) -> tuple[int, int, int]:
    """RGBA → RGB（折叠透明度，物理 LED 无 alpha）。"""
    o = c[3]
    return (round(c[0] * o), round(c[1] * o), round(c[2] * o))
