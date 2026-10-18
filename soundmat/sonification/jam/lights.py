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
        self._idx = np.arange(led_count)
        self._cardinal_idx = np.array(sorted(self.cardinals))
        self._cardinal_rgb = np.array([RED_FULL if i == 0 else RED_MUTED for i in sorted(self.cardinals)], dtype=np.float64)
        self._sweep_op = np.array(SWEEP_OPACITY_BY_DIST + [0.0] * led_count, dtype=np.float64)
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

    def _cardinal_rgba(self, t: float) -> tuple[np.ndarray, float]:
        op = CARDINAL_BREATH_MIN + (1 - CARDINAL_BREATH_MIN) * breath_phase(t)
        return self._cardinal_rgb, max(0.0, min(1.0, op))

    def render(self, t: float, *, state: str, sweep: float, stones: list[tuple[int, int]]) -> LightLayer:
        """``state``：idle / playing / ended；``sweep``：扫描线位置（扇区）；``stones``：触发环上的 (环, 扇区)。

        整圈灯珠一起用 numpy 计算（每秒 60 次，在声音化的节拍线程里）。逐灯珠的写法在 Pi 3B 上
        单这一步就要占大半个核；结果与它逐像素一致（tests/test_jam_lights.py 保留了逐灯珠实现作对照）。
        """
        n = self.n
        self.previews = [p for p in self.previews if t - p[0] < PREVIEW_DURATION + 0.1]
        self.flashes = [f for f in self.flashes if t - f[0] < SCAN_HIT_DURATION + 0.05]

        rgb = np.zeros((n, 3), dtype=np.float64)       # 0–255
        rgb[:] = WHITE
        alpha = np.zeros(n, dtype=np.float64)
        card_rgb, card_a = self._cardinal_rgba(t)
        cards = self._cardinal_idx

        if state == "idle":
            alpha[:] = max(0.0, min(1.0, breath_phase(t) * IDLE_BREATH_MAX / 255))
        elif state == "playing":
            behind = (self.led_for_sector(sweep) - self._idx) % n
            trail = (behind <= n // 2) & (behind <= SWEEP_TRAIL_WIDTH)
            alpha[trail] = self._sweep_op[behind[trail]]
            # 石头标记：按石头的顺序叠加，同一颗灯上的多个标记依次混合。涉及的灯不多，用普通数值逐个算
            # 比反复调用 numpy 的小数组运算快得多，最后一次写回
            m = 0.55
            marked: dict[int, list[float]] = {}
            for ring, sector in stones:
                c = self.led_for_sector(sector)
                cr, cg, cb = RING_COLORS[ring]
                for i in ((c - 1) % n, c, (c + 1) % n):
                    v = marked.get(i)
                    if v is None:
                        v = marked[i] = [255.0, 255.0, 255.0, float(alpha[i])]
                    v[0] = v[0] * (1 - m) + cr * m
                    v[1] = v[1] * (1 - m) + cg * m
                    v[2] = v[2] * (1 - m) + cb * m
                    v[3] = min(1.0, v[3] * (1 - m) + 0.22 * m)
            if marked:
                idx = np.fromiter(marked.keys(), dtype=np.intp, count=len(marked))
                vals = np.array(list(marked.values()))
                rgb[idx] = vals[:, :3]
                alpha[idx] = vals[:, 3]
        rgb[cards] = card_rgb
        alpha[cards] = card_a

        if state != "ended" and self.previews:
            best = np.zeros(n)
            col = np.zeros((n, 3))
            for start, sector, ring in self.previews:
                c = self.led_for_sector(sector)
                span = np.unique([(c + d) % n for d in range(-2, 3)])
                m = pulse_mix(t - start)
                win = span[m > best[span]]
                best[win] = m
                col[win] = RING_COLORS[ring]
            b = np.clip(best, 0.0, 1.0)
            on = b > 0
            rgb[on] = rgb[on] * (1 - b[on, None]) + col[on] * b[on, None]
            alpha[on] = np.minimum(1.0, alpha[on] * (1 - b[on]) + b[on])

        if state == "playing" and self.flashes:
            strength = np.zeros(n)
            col = np.zeros((n, 3))
            for start, sector, ring in self.flashes:
                c = self.led_for_sector(sector)
                mix = scan_hit_mix(t - start)
                for off in sorted(SCAN_HIT_OFFSETS):
                    i = (c + off) % n
                    m = mix * SCAN_HIT_FALLOFF[min(abs(off), 2)]
                    if m > strength[i]:
                        strength[i] = m
                        col[i] = RING_COLORS[ring]
            hit_a = np.clip(strength, 0.0, 1.0)
            lum = lambda c, a: (c[:, 0] * 0.299 + c[:, 1] * 0.587 + c[:, 2] * 0.114) * a
            take = (strength > 0.02) & (lum(col, hit_a) >= lum(rgb, alpha))
            rgb[take] = col[take]
            alpha[take] = hit_a[take]

        return LightLayer("jam", 0, (rgb / 255).astype(np.float32), alpha.astype(np.float32))
