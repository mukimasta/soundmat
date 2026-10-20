"""灯光层的绘制工具，各模式共用。灯环逻辑位置 0 在 12 点方向（0°），顺时针编号。

画布上的颜色用 0–255 的 RGB，不透明度 0–1，``Canvas.layer()`` 再换算成灯光层的 0–1。
整圈的操作（铺底、扫描尾迹、按条件替换）用 numpy 一起算；石头标记这类只涉及少数几颗灯、
而且同一颗灯上要按顺序依次叠加的操作，先用普通数值逐个算好再一次写回，比反复调用 numpy 的
小数组运算快得多（在 Pi 3B 上，逐灯珠的写法单灯光一步就要占大半个核）。
"""
from __future__ import annotations

import math
from typing import Iterable, Mapping, Sequence

import numpy as np

from ..intent import LightIntent, LightLayer
from ..perception.zones import OUTER_ZONES, ZONES

RING_COLORS = (
    (100, 108, 128), (148, 112, 88), (88, 72, 210), (32, 188, 148),
    (48, 152, 255), (200, 72, 168), (218, 158, 48), (255, 108, 32),
)

WARM = (255, 180, 90)

Color = Sequence[float]


def led_for_angle(angle: float, led_count: int) -> int:
    """角度（度）→ 最近的逻辑灯珠位置。"""
    return int(round((angle % 360.0) / 360.0 * led_count)) % led_count


def led_for_sector(sector: float, led_count: int) -> int:
    """外圈扇区（0–32，可以是小数，例如扫描线的位置）→ 最近的逻辑灯珠位置。"""
    return int(round((sector % OUTER_ZONES) / OUTER_ZONES * led_count)) % led_count


def around(center: int, radius: int, led_count: int) -> list[int]:
    """以 ``center`` 为中心、两侧各 ``radius`` 颗的灯珠位置（绕圈）。"""
    return [(center + d) % led_count for d in range(-radius, radius + 1)]


def span(center: int, width: int, color: Color, alpha: float, led_count: int) -> list[tuple[int, Color, float]]:
    """以 ``center`` 为中心的 ``width`` 颗灯，两侧按距离减弱：给 ``Canvas.add`` 的标记。"""
    half = max(0, width // 2)
    return [((center + d) % led_count, color, alpha * (1.0 - abs(d) / (half + 1)))
            for d in range(-half, half + 1)]


def luminance(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """按不透明度折算后的亮度，用来比较两种颜色哪个更显眼。"""
    return (rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114) * alpha


class Glow:
    """几处光同时落在一颗灯上时，取最强的那一处（颜色跟着它走）。例如预听和扫描命中。"""

    def __init__(self, led_count: int):
        self.strength = np.zeros(led_count)
        self.rgb = np.zeros((led_count, 3))

    def add(self, indices: Sequence[int], strength, color: Color) -> None:
        """在 ``indices``（互不相同）上加一处光，``strength`` 是一个数或每颗灯一个数。只覆盖更弱的。"""
        idx = np.asarray(indices, dtype=np.intp)
        s = np.broadcast_to(np.asarray(strength, dtype=np.float64), idx.shape)
        win = s > self.strength[idx]
        self.strength[idx[win]] = s[win]
        self.rgb[idx[win]] = color


class Canvas:
    """画一层灯光。``rgb`` 为 (N, 3) 的 0–255 颜色，``alpha`` 为 (N,) 的不透明度。"""

    def __init__(self, led_count: int, color: Color = (0, 0, 0), alpha: float = 0.0):
        self.n = led_count
        self.index = np.arange(led_count)
        self.rgb = np.empty((led_count, 3))
        self.alpha = np.empty(led_count)
        self.fill(color, alpha)

    def fill(self, color: Color, alpha: float) -> "Canvas":
        self.rgb[:] = color
        self.alpha[:] = _clip(alpha)
        return self

    def paint(self, indices, color, alpha) -> None:
        """直接覆盖这些位置的颜色和不透明度（``color`` 可以是一种颜色或每颗灯一种）。"""
        self.rgb[indices] = color
        self.alpha[indices] = np.clip(alpha, 0.0, 1.0)

    def blend(self, marks: Iterable[tuple[int, Color]], mix: float, alpha: float) -> None:
        """按顺序把每个标记的灯朝它的颜色混合 ``mix``，不透明度朝 ``alpha`` 混合；
        同一颗灯上的多个标记依次叠加（例如 Jam 里相邻石头的标记）。"""
        touched: dict[int, list[float]] = {}
        for i, (cr, cg, cb) in marks:
            v = touched.get(i)
            if v is None:
                r, g, b = self.rgb[i]
                v = touched[i] = [float(r), float(g), float(b), float(self.alpha[i])]
            v[0] = v[0] * (1 - mix) + cr * mix
            v[1] = v[1] * (1 - mix) + cg * mix
            v[2] = v[2] * (1 - mix) + cb * mix
            v[3] = min(1.0, v[3] * (1 - mix) + alpha * mix)
        self._write(touched)

    def add(self, marks: Iterable[tuple[int, Color, float]]) -> None:
        """按顺序叠加标记 (位置, 颜色, 不透明度)：不透明度取较大者，颜色按两者的不透明度加权混合
        （例如 Ambient 的石头标记，见 ``span``）。"""
        touched: dict[int, list[float]] = {}
        for i, (cr, cg, cb), a in marks:
            v = touched.get(i)
            if v is None:
                r, g, b = self.rgb[i]
                v = touched[i] = [float(r), float(g), float(b), float(self.alpha[i])]
            a0 = v[3]
            if max(a0, a) <= 0:
                continue
            w = a / (a0 + a) if (a0 + a) > 0 else 1.0
            v[0] = v[0] * (1 - w) + cr * w
            v[1] = v[1] * (1 - w) + cg * w
            v[2] = v[2] * (1 - w) + cb * w
            v[3] = max(a0, a)
        self._write(touched)

    def tint(self, glow: Glow) -> None:
        """每颗灯按光的强度朝光的颜色混合，强度为 1 时完全变成光的颜色、完全不透明（例如预听）。"""
        b = np.clip(glow.strength, 0.0, 1.0)
        on = b > 0
        self.rgb[on] = self.rgb[on] * (1 - b[on, None]) + glow.rgb[on] * b[on, None]
        self.alpha[on] = np.minimum(1.0, self.alpha[on] * (1 - b[on]) + b[on])

    def outshine(self, glow: Glow, threshold: float = 0.0) -> None:
        """光比原来的颜色更显眼（亮度不低于原来）的地方，直接换成光（例如扫描命中）。"""
        a = np.clip(glow.strength, 0.0, 1.0)
        take = (glow.strength > threshold) & (luminance(glow.rgb, a) >= luminance(self.rgb, self.alpha))
        self.rgb[take] = glow.rgb[take]
        self.alpha[take] = a[take]

    def layer(self, name: str, priority: int) -> LightLayer:
        return LightLayer(name, priority, (self.rgb / 255).astype(np.float32), self.alpha.astype(np.float32))

    def _write(self, touched: dict[int, list[float]]) -> None:
        if touched:
            idx = np.fromiter(touched.keys(), dtype=np.intp, count=len(touched))
            vals = np.array(list(touched.values()))
            self.rgb[idx] = vals[:, :3]
            self.alpha[idx] = vals[:, 3]


def _clip(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def breathing_marks(t: float, occupied: Iterable[int], led_count: int) -> LightIntent:
    """Ambient 模式的灯光：暖色的整体呼吸作底色，有石头的位置叠加这一环颜色的淡淡标记。"""
    breath = 0.25 + 0.2 * (0.5 + 0.5 * math.sin(t * 0.9))
    base = Canvas(led_count, WARM, breath)
    marks = Canvas(led_count)
    marks.add(m for z in occupied
              for m in span(led_for_angle(ZONES[z].center_deg, led_count), 3, RING_COLORS[ZONES[z].ring], 0.55,
                            led_count))
    return LightIntent((base.layer("base", 0), marks.layer("stones", 10)))


def warm_breathing(level: float, stones: Mapping[int, float], led_count: int, *, color: Color,
                   breath_min: float, breath_max: float, stone_alpha: float, stone_width: int) -> LightIntent:
    """声池模式（《冥想》）的灯光：一种颜色的整圈呼吸，有石头的位置同一种颜色、更亮一些。
    ``level`` 是 0–1 的明暗（声池模式里是呼吸，与底音的音量起伏同一条曲线），映射到 ``breath_min``–``breath_max``；
    ``stones`` 是区域 → 石头标记的强度（0–1，渐亮渐暗由模式算），标记以石头方位为中心、两侧各
    ``stone_width`` 颗，向两侧减弱，亮度是 ``stone_alpha`` 乘强度。"""
    base = Canvas(led_count, color, breath_min + (breath_max - breath_min) * level)
    marks = Canvas(led_count)
    marks.add(m for z, k in stones.items()
              for m in span(led_for_angle(ZONES[z].center_deg, led_count), 2 * stone_width + 1, color,
                            stone_alpha * k, led_count))
    return LightIntent((base.layer("base", 0), marks.layer("stones", 10)))
