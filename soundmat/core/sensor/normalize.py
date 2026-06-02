"""S 帧 wire 矩阵方向归一化（与 Jam / Web 顺时针 sector 约定对齐）。

全环统一列反转 ``slice s ↔ 31-s``，保证内外圈热力图同一角度对齐。
内圈 R0–R1 的有效数据改在 ``map._pre_offset_row`` 从奇数 slice 读取（见 map.py）。
"""
from __future__ import annotations

import numpy as np

from ... import config


def normalize_wire_matrix(wire: np.ndarray, *, mirror: bool | None = None) -> np.ndarray:
    """可选 slice 镜像：全环 ``[:, ::-1]``。"""
    w = np.asarray(wire, dtype=np.int16)
    if w.shape != (config.NUM_RINGS, config.NUM_SLICES):
        raise ValueError(f"expected shape ({config.NUM_RINGS}, {config.NUM_SLICES}), got {w.shape}")
    do_mirror = config.WIRE_SLICE_MIRROR if mirror is None else mirror
    if not do_mirror:
        return w.copy()
    out = w.copy()
    out[:, :] = out[:, ::-1]
    return out
