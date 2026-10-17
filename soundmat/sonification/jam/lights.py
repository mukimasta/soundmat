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

from ..intent import LightLayer
from ..lights import RING_COLORS

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

RGBA = tuple[float, float, float, float]


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


def _rgba(rgb, op: float) -> RGBA:
    return (rgb[0], rgb[1], rgb[2], max(0.0, min(1.0, op)))


def _lum(c: RGBA) -> float:
    return (c[0] * 0.299 + c[1] * 0.587 + c[2] * 0.114) * c[3]


def _blend(base: RGBA, over: RGBA, mix: float) -> RGBA:
    m = max(0.0, min(1.0, mix))
    if m <= 0:
        return base
    return (base[0] * (1 - m) + over[0] * m, base[1] * (1 - m) + over[1] * m,
            base[2] * (1 - m) + over[2] * m, min(1.0, base[3] * (1 - m) + over[3] * m))


class JamLights:
    def __init__(self, led_count: int):
        self.n = led_count
        self.cardinals = {0, led_count // 4, led_count // 2, 3 * led_count // 4}
        self.previews: list[tuple[float, int, int]] = []   # (开始时刻, 扇区, 环)
        self.flashes: list[tuple[float, int, int]] = []

    def led_for_sector(self, sector: float) -> int:
        return int(round((sector % 32) / 32 * self.n)) % self.n

    def preview(self, t: float, sector: int, ring: int) -> None:
        self.previews.append((t, sector, ring))

    def flash(self, t: float, sector: int, ring: int) -> None:
        self.flashes.append((t, sector, ring))

    def _cardinal(self, i: int, t: float) -> RGBA:
        op = CARDINAL_BREATH_MIN + (1 - CARDINAL_BREATH_MIN) * breath_phase(t)
        return _rgba(RED_FULL if i == 0 else RED_MUTED, op)

    def render(self, t: float, *, state: str, sweep: float, stones: list[tuple[int, int]]) -> LightLayer:
        """``state``：idle / playing / ended；``sweep``：扫描线位置（扇区）；``stones``：触发环上的 (环, 扇区)。"""
        n = self.n
        self.previews = [p for p in self.previews if t - p[0] < PREVIEW_DURATION + 0.1]
        self.flashes = [f for f in self.flashes if t - f[0] < SCAN_HIT_DURATION + 0.05]

        markers: dict[int, list[int]] = {}
        if state == "playing":
            for ring, sector in stones:
                c = self.led_for_sector(sector)
                for d in (-1, 0, 1):
                    markers.setdefault((c + d) % n, []).append(ring)
        sweep_led = self.led_for_sector(sweep)
        preview_spans = [(p, {(self.led_for_sector(p[1]) + d) % n for d in range(-2, 3)}) for p in self.previews]

        rgb = np.zeros((n, 3), dtype=np.float32)
        alpha = np.zeros(n, dtype=np.float32)
        for i in range(n):
            if state == "ended":
                base = self._cardinal(i, t) if i in self.cardinals else _rgba(WHITE, 0.0)
            elif state == "idle":
                base = self._cardinal(i, t) if i in self.cardinals else _rgba(WHITE, breath_phase(t) * IDLE_BREATH_MAX / 255)
            else:
                base = _rgba(WHITE, 0.0)
                behind = (sweep_led - i) % n
                if behind <= n // 2 and behind <= SWEEP_TRAIL_WIDTH:
                    base = _rgba(WHITE, SWEEP_OPACITY_BY_DIST[behind])
                for ring in markers.get(i, ()):
                    base = _blend(base, _rgba(RING_COLORS[ring], 0.22), 0.55)
                if i in self.cardinals:
                    base = self._cardinal(i, t)

            if state != "ended":
                best, ring = 0.0, None
                for (start, _, r), span in preview_spans:
                    if i in span:
                        m = pulse_mix(t - start)
                        if m > best:
                            best, ring = m, r
                if best > 0:
                    base = _blend(base, _rgba(RING_COLORS[ring], 1.0), best)

            if state == "playing":
                strength, ring = 0.0, None
                for start, sector, r in self.flashes:
                    off = (i - self.led_for_sector(sector)) % n
                    if off > n // 2:
                        off -= n
                    if off not in SCAN_HIT_OFFSETS:
                        continue
                    m = scan_hit_mix(t - start) * SCAN_HIT_FALLOFF[min(abs(off), 2)]
                    if m > strength:
                        strength, ring = m, r
                if strength > 0.02:
                    hit = _rgba(RING_COLORS[ring], strength)
                    if _lum(hit) >= _lum(base):
                        base = hit

            rgb[i] = (base[0] / 255, base[1] / 255, base[2] / 255)
            alpha[i] = base[3]
        return LightLayer("jam", 0, rgb, alpha)
