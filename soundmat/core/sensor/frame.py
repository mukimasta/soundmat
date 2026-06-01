"""S 帧解析（固件设计文档 §串口数据模块）。

帧格式（ASCII 文本，921600 baud）：

    S:v0,v1,v2,...,v255*XX\\n

256 个十进制整数（ring-major：index = ring*32 + slice），值域 -1..4095
（12-bit ADC 原始值，-1 表示无效）。`XX` 是从 TYPE 字符到 `*` 前最后一字符（含
`S` 和 `:`）所有字节的 XOR 校验，2 位大写十六进制。

本模块只做解码与校验，不做聚类/阈值——那是 jam/ambient 各自 sensor_state 的事。
"""
from __future__ import annotations

import numpy as np

from ... import config

__all__ = ["parse_sensor_frame", "compute_checksum", "FrameError"]


class FrameError(ValueError):
    """帧格式错误（长度不符、校验失败、非法值）。校验失败按设计直接丢弃，不重传。"""


def compute_checksum(payload: bytes) -> int:
    """对给定字节序列做 XOR，返回 0-255 的校验值。"""
    chk = 0
    for b in payload:
        chk ^= b
    return chk


def parse_sensor_frame(line: str, *, verify: bool = True) -> np.ndarray:
    """解析一行 S 帧（不含末尾 \\n），返回长度 256 的 int16 数组（ring-major）。

    Args:
        line: 形如 ``S:1,2,...,255*A7`` 的一行（已去掉 \\n）。
        verify: 是否校验 XOR；失败抛 FrameError。

    Returns:
        np.ndarray shape (256,) dtype int16，值域 -1..4095。
    """
    line = line.strip()
    if not line.startswith(config.SERIAL_FRAME_SENSOR + ":"):
        raise FrameError(f"非 S 帧: {line[:16]!r}")

    star = line.rfind("*")
    if star < 0:
        raise FrameError("缺少校验分隔符 '*'")

    body = line[: star]          # "S:....."（含 TYPE 和 ':'），参与校验
    checksum_hex = line[star + 1:]
    payload = line[2:star]       # ':' 之后到 '*' 之前的数字串

    if verify:
        try:
            expected = int(checksum_hex, 16)
        except ValueError as e:
            raise FrameError(f"非法校验码 {checksum_hex!r}") from e
        actual = compute_checksum(body.encode("ascii"))
        if actual != expected:
            raise FrameError(f"校验失败: 期望 {expected:02X} 实得 {actual:02X}")

    parts = payload.split(",")
    if len(parts) != config.SENSOR_VALUES:
        raise FrameError(
            f"值数量 {len(parts)} != {config.SENSOR_VALUES}"
        )
    try:
        values = np.fromiter((int(p) for p in parts), dtype=np.int16, count=len(parts))
    except ValueError as e:
        raise FrameError(f"非法整数: {e}") from e
    return values


def values_to_matrix(values: np.ndarray) -> np.ndarray:
    """256 值 → (NUM_RINGS, NUM_SLICES) 矩阵，ring-major。"""
    return values.reshape(config.NUM_RINGS, config.NUM_SLICES)
