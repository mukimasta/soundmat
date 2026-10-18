"""Jam 灯光：向量化实现必须与第一版移植来的逐灯珠实现逐像素一致（这里保留逐灯珠实现作对照）。"""
import random

import numpy as np
import pytest

from soundmat.intent import LightLayer
from soundmat.sonification.lights import RING_COLORS
from soundmat.sonification.jam.lights import (
    CARDINAL_BREATH_MIN, IDLE_BREATH_MAX, PREVIEW_DURATION, RED_FULL, RED_MUTED, SCAN_HIT_DURATION,
    SCAN_HIT_FALLOFF, SCAN_HIT_OFFSETS, SWEEP_OPACITY_BY_DIST, SWEEP_TRAIL_WIDTH, WHITE, JamLights,
    breath_phase, pulse_mix, scan_hit_mix,
)

RGBA = tuple[float, float, float, float]


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


class ReferenceJamLights:
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


@pytest.mark.parametrize("seed", range(40))
def test_vectorized_matches_reference(seed):
    rnd = random.Random(seed)
    new, old = JamLights(108), ReferenceJamLights(108)
    t = rnd.uniform(0, 100)
    for _ in range(rnd.randint(0, 6)):
        args = (t - rnd.uniform(-0.1, 1.2), rnd.randint(0, 31), rnd.randint(2, 7))
        new.preview(*args); old.preview(*args)
    for _ in range(rnd.randint(0, 8)):
        args = (t - rnd.uniform(-0.05, 0.3), rnd.randint(0, 31), rnd.randint(2, 7))
        new.flash(*args); old.flash(*args)
    stones = [(rnd.randint(2, 7), rnd.randint(0, 31)) for _ in range(rnd.randint(0, 60))]
    for state in ("idle", "playing", "ended"):
        sweep = rnd.uniform(0, 32)
        a = new.render(t, state=state, sweep=sweep, stones=stones)
        b = old.render(t, state=state, sweep=sweep, stones=stones)
        np.testing.assert_allclose(a.rgb, b.rgb, atol=1e-5)
        np.testing.assert_allclose(a.alpha, b.alpha, atol=1e-5)
