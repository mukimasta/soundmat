"""垫面信号：把原始读数变成干净、对齐的压力图（ARCHITECTURE「感知」）。

1. 校准：无效读数（-1）当作 0；需要时反相；除以满量程得到 0–1 的归一化压力。
2. 坐标对齐：物理接线（8 环 × 32 接线扇区）→ 224 个区域。

坐标对齐严格沿用第一版（``core/sensor/normalize.py`` + ``core/sensor/map.py``），因为扇区偏移 4、
灯带偏移 101 都是在这套规则下校准的（DECISION 第 7 条）：

- 整个接线矩阵先做扇区镜像（接线扇区 s ↔ 31 − s）；
- 外环（第 2–7 环）：镜像后的接线扇区直接对应逻辑扇区；
- 内环（第 0、1 环）：只有一半接线扇区有电极。镜像后从奇数接线扇区 2(15−k)+1 读出，放到逻辑扇区 2k+1；
  两次镜像相互抵消，结果是内环其实没有被镜像：逻辑扇区 2k+1 取原始接线扇区 2k；
- 最后整体顺时针旋转 ``sector_offset`` 个扇区：逻辑扇区 sec 取旋转前的 (sec − offset) mod 32。

外环第 j 区就是逻辑扇区 j；内环第 j 区是逻辑扇区 2j+1（见 ``zones.py``）。这些规则在模块加载时
算成一张"区域 → 接线序号"的索引表，每帧只做一次取值。
"""
from __future__ import annotations

import numpy as np

from ...config import MatConfig
from ..model import PressureMap
from ..zones import INNER_RINGS, INNER_ZONES, NUM_RINGS, OUTER_ZONES, ZONES

WIRE_SLICES = 32


def logical_from_wire(wire: np.ndarray, mirror: bool, offset: int) -> np.ndarray:
    """第一版的映射，逐步照搬：接线矩阵 (8, 32) → 逻辑矩阵 (8, 32)。内环偶数逻辑扇区恒为 -1。"""
    w = np.asarray(wire)
    if mirror:
        w = w[:, ::-1]
    out = np.full_like(w, -1)
    for ring in range(NUM_RINGS):
        pre = np.full(WIRE_SLICES, -1, dtype=w.dtype)
        if ring < INNER_RINGS:
            for k in range(INNER_ZONES):
                pre[2 * k + 1] = w[ring, 2 * (INNER_ZONES - 1 - k) + 1] if mirror else w[ring, 2 * k]
        else:
            pre[:] = w[ring]
        for sec in range(WIRE_SLICES):
            out[ring, sec] = pre[(sec - offset) % WIRE_SLICES]
    return out


def zone_wire_index(mirror: bool, offset: int) -> np.ndarray:
    """每个区域取自哪个接线读数（环 × 32 + 接线扇区）。"""
    ids = np.arange(NUM_RINGS * WIRE_SLICES).reshape(NUM_RINGS, WIRE_SLICES)
    logical = logical_from_wire(ids, mirror, offset)
    out = np.empty(len(ZONES), dtype=np.int64)
    for z in ZONES:
        sector = 2 * z.slot + 1 if z.ring < INNER_RINGS else z.slot
        out[z.index] = logical[z.ring, sector]
    assert (out >= 0).all() and len(set(out.tolist())) == len(out)
    return out


class Signal:
    def __init__(self, cfg: MatConfig):
        self.cfg = cfg
        self.index = zone_wire_index(cfg.sector_mirror, cfg.sector_offset)
        assert OUTER_ZONES == WIRE_SLICES

    def pressure(self, t: float, seq: int, values: np.ndarray) -> PressureMap:
        raw = np.asarray(values, dtype=np.float32)[self.index]
        invalid = raw < 0
        if self.cfg.invert:
            raw = self.cfg.full_scale - raw
        raw[invalid] = 0.0
        p = np.clip(raw / self.cfg.full_scale, 0.0, 1.0).astype(np.float32)
        return PressureMap(t=t, seq=seq, values=p)
