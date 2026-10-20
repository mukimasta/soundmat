"""垫面信号：外环的坐标对齐与第一版一致（移植 test_sensor_map / test_wire_normalize 的断言）；内环按真垫子实测改正。"""
import numpy as np
import pytest

from soundmat.config import MatConfig
from soundmat.perception.signal import Signal, logical_from_wire, zone_wire_index
from soundmat.perception.zones import zone

OFF = 4


def wire():
    return np.zeros((8, 32), dtype=np.int64)


def test_outer_mirror_then_offset():
    w = wire()
    w[7, 10] = 2000
    logical = logical_from_wire(w, mirror=True, offset=OFF)
    # 镜像：接线 10 → 21；旋转 4：逻辑 25
    assert logical[7, (21 + OFF) % 32] == 2000
    w = wire()
    w[7, 10] = 2000
    assert logical_from_wire(w, mirror=False, offset=OFF)[7, (10 + OFF) % 32] == 2000


def test_inner_rings_mirror_like_outer_and_ignore_odd_slices():
    w = wire()
    w[0, 0] = 3000
    w[0, 1] = 9999           # 奇数接线扇区没有电极，忽略
    logical = logical_from_wire(w, mirror=True, offset=OFF)
    assert logical[0, (31 + OFF) % 32] == 3000     # 与外环一样：接线 0 → 镜像 31 → 旋转 4
    assert 9999 not in logical


def test_inner_zone_lines_up_with_outer_on_the_same_radius():
    """2026-10-20 真垫子实测：沿一条径向线同时按，外环第 k 区与内环接线扇区 w 一起亮。"""
    from soundmat.perception.zones import zone as zn
    idx = zone_wire_index(True, OFF)
    for k, w in [(2, 2), (4, 0), (6, 30), (8, 28)]:
        inner = next(z for z in range(16) if idx[z] == w)
        outer, z = zn(7, k), zn(0, inner)
        assert abs((outer.center_deg - z.center_deg + 180) % 360 - 180) < z.span_deg / 2


def test_v1_reader_example_outer_27():
    # 第一版 test_reader_emit_applies_mirror：接线 [7, 4] 镜像后在 [7, 27]
    w = wire()
    w[7, 4] = 500
    logical = logical_from_wire(w, mirror=True, offset=0)
    assert logical[7, 27] == 500


def test_zone_index_is_a_bijection_onto_used_wires():
    idx = zone_wire_index(True, OFF)
    assert len(idx) == 224 and len(set(idx.tolist())) == 224
    # 外环第 j 区 = 逻辑扇区 j；内环只用偶数接线扇区
    assert idx[zone(7, (21 + OFF) % 32).index] == 7 * 32 + 10
    assert all(idx[zone(r, j).index] % 2 == 0 for r in (0, 1) for j in range(16))


def test_pressure_calibration():
    s = Signal(MatConfig())
    vals = np.full(256, -1, dtype=np.int16)
    vals[7 * 32 + 10] = 4095
    vals[2 * 32 + 0] = 500
    p = s.pressure(1.0, 7, vals)
    assert p.seq == 7 and p.values.max() == 1.0
    assert p.values[zone(7, 25).index] == 1.0
    assert (p.values >= 0).all()
    assert p.values[zone(2, (31 + OFF) % 32).index] == pytest.approx(500 / 4095)
    inv = Signal(MatConfig(invert=True)).pressure(1.0, 1, np.full(256, 4095, dtype=np.int16))
    assert inv.values.max() == 0.0
