"""控制器串口协议（系列文档第 7 篇，沿用第一版）：921600 波特，ASCII 文本帧，每行一帧。

- 上行 S 帧：``S:v0,v1,...,v255*XX``，256 个十进制整数（环优先：序号 = 环 × 32 + 接线扇区），
  值域 -1..4095（12 位 ADC，-1 表示无效）。
- 下行 L 帧：``L:RRGGBB,...*XX``，每颗灯一个 6 位十六进制，顺序 R、G、B（固件内部转 GRB）。
- 调试行以 ``#`` 开头，无校验，接收方丢弃。
- ``XX`` 是从帧类型字符到 ``*`` 之前所有字节的 XOR，2 位大写十六进制。
"""
from __future__ import annotations

import numpy as np

SENSOR_VALUES = 256
BAUD = 921600


class FrameError(ValueError):
    """帧格式错误；校验失败的帧直接丢弃，不重传。"""


def checksum(payload: bytes) -> int:
    c = 0
    for b in payload:
        c ^= b
    return c


def parse_sensor_frame(line: str) -> np.ndarray:
    """解析一行 S 帧（不含换行），返回 256 个 int16（环优先的接线矩阵）。"""
    line = line.strip()
    if not line.startswith("S:"):
        raise FrameError(f"不是 S 帧：{line[:16]!r}")
    star = line.rfind("*")
    if star < 0:
        raise FrameError("缺少校验分隔符")
    try:
        expected = int(line[star + 1:], 16)
    except ValueError as e:
        raise FrameError("非法校验码") from e
    actual = checksum(line[:star].encode("ascii", errors="replace"))
    if actual != expected:
        raise FrameError(f"校验失败：期望 {expected:02X}，实得 {actual:02X}")
    parts = line[2:star].split(",")
    if len(parts) != SENSOR_VALUES:
        raise FrameError(f"值数量 {len(parts)} ≠ {SENSOR_VALUES}")
    try:
        return np.array([int(p) for p in parts], dtype=np.int16)
    except ValueError as e:
        raise FrameError(f"非法整数：{e}") from e


def encode_sensor_frame(values) -> str:
    """测试与模拟控制器用：把 256 个整数编码成 S 帧（含换行）。"""
    body = "S:" + ",".join(str(int(v)) for v in values)
    return f"{body}*{checksum(body.encode('ascii')):02X}\n"


def encode_led_frame(colors: np.ndarray) -> bytes:
    """(N, 3) 的 0–255 颜色 → 一行 L 帧（含换行）。"""
    c = np.clip(np.asarray(colors), 0, 255).astype(np.uint8)
    body = "L:" + ",".join(f"{r:02X}{g:02X}{b:02X}" for r, g, b in c)
    return f"{body}*{checksum(body.encode('ascii')):02X}\n".encode("ascii")
