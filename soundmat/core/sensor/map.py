"""S → L 坐标映射（设计文档 §13）。

- S (wire): ``matrix[ring, slice]`` — S 帧 / 串口原始格，slice ∈ [0, 31]
- L (logic): ``L_adc[ring, sector]`` — 逻辑压力；threshold 与 occupied 用 sector

内圈 R0–R1（offset 之前）：
  - 奇数 slice 丢弃；偶数 slice 2k → 奇数 sector 2k+1；偶数 sector 恒 0
  - wire 列镜像后：从奇数 slice 2(15−k)+1 读回（见 ``_pre_offset_row``）
外圈 R2–R7（offset 之前）：slice 与 sector 一一对应

最后对 pre-offset 的 32 格做全局旋转：
  ``L_adc[r, sec] = pre[(sec - SECTOR_OFFSET) % 32]``
"""
from __future__ import annotations

import numpy as np

from ... import config


def _pre_offset_row(ring: int, wire_row: np.ndarray) -> np.ndarray:
    """单环 wire → pre-offset 逻辑 ADC（长度 32）。

    内圈 R0–R1：默认偶数 slice 2k → pre[2k+1]。
    若已做 wire 列镜像，原偶数格落到奇数 slice 2(15−k)+1，改从奇数 slice 读。
    """
    pre = np.zeros(config.NUM_SLICES, dtype=np.int16)
    if ring < config.INNER_RINGS:
        for k in range(config.INNER_SLICES):
            if config.WIRE_SLICE_MIRROR:
                pre[2 * k + 1] = wire_row[2 * (config.INNER_SLICES - 1 - k) + 1]
            else:
                pre[2 * k + 1] = wire_row[2 * k]
    else:
        pre[:] = wire_row
    return pre


def wire_to_logical_adc(wire: np.ndarray) -> np.ndarray:
    """Wire 矩阵 (8, 32) → 逻辑压力矩阵 L_adc (8, 32)。"""
    wire = np.asarray(wire, dtype=np.int16)
    if wire.shape != (config.NUM_RINGS, config.NUM_SLICES):
        raise ValueError(f"expected shape ({config.NUM_RINGS}, {config.NUM_SLICES}), got {wire.shape}")

    offset = int(config.SECTOR_OFFSET) % config.NUM_SLICES
    out = np.zeros_like(wire)
    for ring in range(config.NUM_RINGS):
        pre = _pre_offset_row(ring, wire[ring])
        for sec in range(config.NUM_SLICES):
            out[ring, sec] = pre[(sec - offset) % config.NUM_SLICES]
    return out
