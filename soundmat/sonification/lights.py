"""灯光层的绘制工具，各模式共用。灯环逻辑位置 0 在 12 点方向（0°），顺时针编号。"""
from __future__ import annotations

import numpy as np

from .intent import LightLayer

RING_COLORS = (
    (100, 108, 128), (148, 112, 88), (88, 72, 210), (32, 188, 148),
    (48, 152, 255), (200, 72, 168), (218, 158, 48), (255, 108, 32),
)


def led_for_angle(angle: float, led_count: int) -> int:
    """角度（度）→ 最近的逻辑灯珠位置。"""
    return int(round((angle % 360.0) / 360.0 * led_count)) % led_count


class Canvas:
    """逐像素画一层灯光，最后生成 ``LightLayer``。颜色用 0–255 的 RGB 表示。"""

    def __init__(self, name: str, priority: int, led_count: int):
        self.name = name
        self.priority = priority
        self.n = led_count
        self.rgb = np.zeros((led_count, 3), dtype=np.float32)
        self.alpha = np.zeros(led_count, dtype=np.float32)

    def fill(self, color, alpha: float) -> "Canvas":
        self.rgb[:] = np.asarray(color, dtype=np.float32) / 255.0
        self.alpha[:] = alpha
        return self

    def put(self, index: int, color, alpha: float) -> None:
        """在一个位置上叠加颜色（不透明度取较大者，颜色按不透明度混合）。"""
        i = index % self.n
        a0 = self.alpha[i]
        a = max(a0, alpha)
        if a <= 0:
            return
        c = np.asarray(color, dtype=np.float32) / 255.0
        w = alpha / (a0 + alpha) if (a0 + alpha) > 0 else 1.0
        self.rgb[i] = self.rgb[i] * (1 - w) + c * w
        self.alpha[i] = a

    def span(self, center: int, width: int, color, alpha: float) -> None:
        """以 ``center`` 为中心画 ``width`` 颗灯，两侧按距离减弱。"""
        half = max(0, width // 2)
        for d in range(-half, half + 1):
            fall = 1.0 - abs(d) / (half + 1)
            self.put(center + d, color, alpha * fall)

    def layer(self) -> LightLayer:
        return LightLayer(self.name, self.priority, self.rgb.copy(), self.alpha.copy())
