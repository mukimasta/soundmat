"""垫面信号：把原始读数变成干净、对齐的压力图（ARCHITECTURE「感知」）。

1. 校准：无效读数（-1）当作 0；需要时反相；除以满量程得到 0–1 的归一化压力。
2. 坐标对齐：物理接线（8 环 × 32 接线扇区）→ 224 个区域。

坐标对齐：

- 整个接线矩阵做扇区镜像（接线扇区 s ↔ 31 − s），再整体顺时针旋转 ``sector_offset`` 个扇区：
  逻辑扇区 sec 取镜像后的 (sec − offset) mod 32。外环第 j 区就是逻辑扇区 j。
  扇区偏移 4 是第一版在这套规则下校准的（DECISION 第 7 条）。
- 内环（第 0、1 环）与外环同样镜像、旋转：扇区电极是从外缘贯穿到内环的径向条，内环只有偶数接线扇区
  有电极，而且变宽，盖住外环 2m − 1、2m 两条接线扇区的角度（2026-10-20 在真垫子上沿径向同时按内外环
  实测：外环接线 2m − 1 的位置，内环亮的是接线 2m）。所以内环第 j 区盖住外环第 2j+1、2j+2 区，
  读其中接线扇区为偶数的那一条（``zones.py``：中心在 (2j + 1.5) × 11.25°）。
  第一版的内环镜像了两次、等于没镜像，方向与外环相反，在真垫子上内外环对不上，已改正。

这些规则在模块加载时算成一张"区域 → 接线序号"的索引表，每帧只做一次取值。
"""
from __future__ import annotations

import numpy as np

from ...config import MatConfig
from ..model import PressureMap
from ..zones import INNER_RINGS, INNER_ZONES, NUM_RINGS, OUTER_ZONES, ZONES

WIRE_SLICES = 32


def logical_from_wire(wire: np.ndarray, mirror: bool, offset: int) -> np.ndarray:
    """接线矩阵 (8, 32) → 逻辑矩阵 (8, 32)：每环都先镜像、再旋转。内环没有电极的接线扇区为 -1。"""
    w = np.array(wire)
    w[:INNER_RINGS, 1::2] = -1                 # 内环只有偶数接线扇区有电极
    if mirror:
        w = w[:, ::-1]
    return np.roll(w, offset, axis=1)          # 逻辑 sec 取 (sec − offset) mod 32


def zone_wire_index(mirror: bool, offset: int) -> np.ndarray:
    """每个区域取自哪个接线读数（环 × 32 + 接线扇区）。"""
    ids = np.arange(NUM_RINGS * WIRE_SLICES).reshape(NUM_RINGS, WIRE_SLICES)
    logical = logical_from_wire(ids, mirror, offset)
    outer_wire = logical[NUM_RINGS - 1] % WIRE_SLICES          # 外环逻辑扇区 → 接线扇区
    out = np.empty(len(ZONES), dtype=np.int64)
    for z in ZONES:
        if z.ring >= INNER_RINGS:
            out[z.index] = logical[z.ring, z.slot]
            continue
        # 内环第 j 区盖住外环逻辑扇区 2j+1、2j+2，它们的接线必须是 2m − 1 和 2m，读偶数的那条
        a, b = (2 * z.slot + 1) % WIRE_SLICES, (2 * z.slot + 2) % WIRE_SLICES
        even, odd = (a, b) if outer_wire[a] % 2 == 0 else (b, a)
        assert (outer_wire[odd] + 1) % WIRE_SLICES == outer_wire[even], \
            f"扇区偏移 {offset} 让内环区跨在两条电极之间"
        out[z.index] = logical[z.ring, even]
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
