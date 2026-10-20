"""垫面区域的几何描述（DATA_MODEL「区域」）。

224 个区域：环 0–7 从内到外；第 0、1 环每环 16 区，第 2–7 环每环 32 区。
角度以 12 点方向为 0°，顺时针增加。

角度约定沿用第一版（扇区偏移 4、灯带偏移 101 都是在这个约定下校准的）：

- 外环第 j 区的中心在 j × 11.25°，跨度 11.25°。
- 内环第 j 区盖住外环第 2j+1、2j+2 区，中心在 (2j + 1.5) × 11.25°（两个外环区之间的缝上），跨度 22.5°；
  两条边界与外环区域的边界对齐，和实物一致（内环的分界线是外环分界线每隔一条延伸进来）。
  第一版把内环中心放在 (2j+1) × 11.25°，差半个外环区，方向也与外环相反（``signal`` 模块说明）。

半径取自控制台设计稿的绘图尺寸（环中心间距约 3.1，环宽 2.75），用于显示和空间化；
``radius`` 是归一化半径：区域中心到圆心的距离除以第 7 环外缘半径。
"""
from __future__ import annotations

from dataclasses import dataclass

NUM_RINGS = 8
INNER_RINGS = 2
INNER_ZONES = 16
OUTER_ZONES = 32
SECTOR_DEG = 360.0 / OUTER_ZONES  # 11.25°

RING_CENTERS = (4.0, 7.107, 10.2145, 13.3215, 16.4285, 19.5355, 22.643, 25.75)
RING_WIDTH = 2.75
MAT_RADIUS = RING_CENTERS[-1] + RING_WIDTH / 2


@dataclass(frozen=True)
class Zone:
    index: int          # 0..223，全局序号（环 0 第 0 区为 0，依次递增）
    ring: int
    slot: int           # 环内序号
    center_deg: float
    span_deg: float
    r_inner: float
    r_outer: float

    @property
    def id(self) -> str:
        return f"{self.ring}:{self.slot}"

    @property
    def radius(self) -> float:
        """归一化半径（0 = 圆心，1 = 垫面外缘）。"""
        return ((self.r_inner + self.r_outer) / 2) / MAT_RADIUS


def zones_in_ring(ring: int) -> int:
    return INNER_ZONES if ring < INNER_RINGS else OUTER_ZONES


def _build() -> tuple[Zone, ...]:
    out = []
    idx = 0
    for ring in range(NUM_RINGS):
        n = zones_in_ring(ring)
        span = 360.0 / n
        for slot in range(n):
            if ring < INNER_RINGS:
                center = (2 * slot + 1.5) * SECTOR_DEG
            else:
                center = slot * SECTOR_DEG
            out.append(Zone(
                index=idx, ring=ring, slot=slot,
                center_deg=center % 360.0, span_deg=span,
                r_inner=RING_CENTERS[ring] - RING_WIDTH / 2,
                r_outer=RING_CENTERS[ring] + RING_WIDTH / 2,
            ))
            idx += 1
    return tuple(out)


ZONES: tuple[Zone, ...] = _build()
NUM_ZONES = len(ZONES)  # 224
_BY_ID = {z.id: z for z in ZONES}
RING_START = tuple(next(z.index for z in ZONES if z.ring == r) for r in range(NUM_RINGS))


def zone(ring: int, slot: int) -> Zone:
    return ZONES[RING_START[ring] + slot]


def zone_by_id(zone_id: str) -> Zone:
    return _BY_ID[zone_id]


def ring_indices(ring: int) -> range:
    return range(RING_START[ring], RING_START[ring] + zones_in_ring(ring))


def geometry_json() -> list[dict]:
    """控制台绘制垫面所需的几何描述。"""
    return [
        {"index": z.index, "id": z.id, "ring": z.ring, "slot": z.slot,
         "center": z.center_deg, "span": z.span_deg,
         "rInner": z.r_inner, "rOuter": z.r_outer}
        for z in ZONES
    ]
