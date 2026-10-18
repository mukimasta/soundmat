"""Jam 灯光（移植自第一版 ``jam/led``，即系列文档第 8 篇的 Jam 灯光方案）。

- 曲终：只有四个方位的红色呼吸，其余熄灭。
- 空闲：整圈暗白呼吸（峰值 20/255），四个方位红色呼吸（75%–100%）。
- 播放：扫描尾迹 + 石头标记 + 四个方位红色呼吸。
- 叠加：预听（余弦淡出 1 秒）与扫描命中（攻击、保持、平方衰减，0.18 秒）。

每个灯珠的状态是 RGBA（0–255 的颜色加不透明度），输出为一个灯光层。
"""
from __future__ import annotations

import math

import numpy as np

from ...intent import LightLayer
from ..lights import RING_COLORS, Canvas, Glow, around, led_for_sector

WHITE = (255, 255, 255)
RED_FULL = (255, 48, 48)
RED_MUTED = (255, 140, 140)
SWEEP_OPACITY_BY_DIST = [1.0, 0.75, 0.40, 0.30, 0.22, 0.15, 0.10, 0.06, 0.03, 0.01, 0.0]
SWEEP_TRAIL_WIDTH = 10
SCAN_HIT_OFFSETS = {0, 1, -1, -2}
SCAN_HIT_FALLOFF = [1.0, 0.82, 0.52]
SCAN_HIT_DURATION = 0.18
SCAN_HOLD = 0.05
PREVIEW_DURATION = 1.0
IDLE_BREATH_MAX = 20
CARDINAL_BREATH_MIN = 0.75
STONE_MIX = 0.55
STONE_ALPHA = 0.22


def breath_phase(t: float) -> float:
    return 0.5 + 0.5 * math.sin(t * 1.35)


def pulse_mix(elapsed: float) -> float:
    if elapsed <= 0:
        return 1.0
    if elapsed >= PREVIEW_DURATION:
        return 0.0
    return 0.5 * (1 + math.cos(math.pi * elapsed / PREVIEW_DURATION))


def scan_hit_mix(elapsed: float) -> float:
    if elapsed < 0:
        return 0.0
    if elapsed <= SCAN_HOLD:
        return 1.0
    if elapsed >= SCAN_HIT_DURATION:
        return 0.0
    x = (elapsed - SCAN_HOLD) / (SCAN_HIT_DURATION - SCAN_HOLD)
    return 1.0 - x * x


class JamLights:
    def __init__(self, led_count: int):
        self.n = led_count
        cardinals = sorted({0, led_count // 4, led_count // 2, 3 * led_count // 4})
        self._cardinal_idx = np.array(cardinals)
        self._cardinal_rgb = np.array([RED_FULL if i == 0 else RED_MUTED for i in cardinals], dtype=np.float64)
        self._sweep_op = np.array(SWEEP_OPACITY_BY_DIST + [0.0] * led_count, dtype=np.float64)
        self.previews: list[tuple[float, int, int]] = []   # (开始时刻, 扇区, 环)
        self.flashes: list[tuple[float, int, int]] = []

    def preview(self, t: float, sector: int, ring: int) -> None:
        self.previews.append((t, sector, ring))

    def flash(self, t: float, sector: int, ring: int) -> None:
        self.flashes.append((t, sector, ring))

    def render(self, t: float, *, state: str, sweep: float, stones: list[tuple[int, int]]) -> LightLayer:
        """``state``：idle / playing / ended；``sweep``：扫描线位置（扇区）；``stones``：触发环上的 (环, 扇区)。

        结果与第一版逐灯珠的写法逐像素一致（tests/test_jam_lights.py 保留了逐灯珠实现作对照）。
        """
        n = self.n
        self.previews = [p for p in self.previews if t - p[0] < PREVIEW_DURATION + 0.1]
        self.flashes = [f for f in self.flashes if t - f[0] < SCAN_HIT_DURATION + 0.05]

        c = Canvas(n, WHITE, 0.0)
        if state == "idle":
            c.fill(WHITE, breath_phase(t) * IDLE_BREATH_MAX / 255)
        elif state == "playing":
            behind = (led_for_sector(sweep, n) - c.index) % n
            trail = (behind <= n // 2) & (behind <= SWEEP_TRAIL_WIDTH)
            c.alpha[trail] = self._sweep_op[behind[trail]]
            c.blend(((i, RING_COLORS[ring]) for ring, sector in stones
                     for i in around(led_for_sector(sector, n), 1, n)), STONE_MIX, STONE_ALPHA)
        c.paint(self._cardinal_idx, self._cardinal_rgb,
                CARDINAL_BREATH_MIN + (1 - CARDINAL_BREATH_MIN) * breath_phase(t))

        if state != "ended" and self.previews:
            glow = Glow(n)
            for start, sector, ring in self.previews:
                glow.add(sorted(set(around(led_for_sector(sector, n), 2, n))), pulse_mix(t - start), RING_COLORS[ring])
            c.tint(glow)

        if state == "playing" and self.flashes:
            glow = Glow(n)
            offsets = sorted(SCAN_HIT_OFFSETS)
            for start, sector, ring in self.flashes:
                center, mix = led_for_sector(sector, n), scan_hit_mix(t - start)
                glow.add([(center + off) % n for off in offsets],
                         [mix * SCAN_HIT_FALLOFF[min(abs(off), 2)] for off in offsets], RING_COLORS[ring])
            c.outshine(glow, threshold=0.02)

        return c.layer("jam", 0)
