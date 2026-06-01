"""Jam LED 渲染：108 颗灯围成一圈，与 32 扇区对齐（设计文档 §6.6 / JAM_DESIGN §7）。

只描述亮灭与颜色，输出 108 路 RGB（已折叠透明度）。LEDWriter 编码成 L 帧发回 ESP32。
"""

from .renderer import JamLedRenderer

__all__ = ["JamLedRenderer"]
