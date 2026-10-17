"""垫面信号：坐标对齐必须与第一版完全一致（移植 test_sensor_map / test_wire_normalize 的断言）。"""
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


def test_inner_even_slice_to_odd_sector_double_mirror_cancels():
    w = wire()
    w[0, 0] = 3000
    w[0, 2] = 2500
    w[0, 1] = 9999           # 奇数接线扇区没有电极，忽略
    logical = logical_from_wire(w, mirror=True, offset=OFF)
    assert logical[0, (1 + OFF) % 32] == 3000
    assert logical[0, (3 + OFF) % 32] == 2500
    assert 9999 not in logical


def test_v1_reader_example_outer_27():
    # 第一版 test_reader_emit_applies_mirror：接线 [7, 4] 镜像后在 [7, 27]
    w = wire()
    w[7, 4] = 500
    logical = logical_from_wire(w, mirror=True, offset=0)
    assert logical[7, 27] == 500


def test_zone_index_is_a_bijection_onto_used_wires():
    idx = zone_wire_index(True, OFF)
    assert len(idx) == 224 and len(set(idx.tolist())) == 224
    # 外环第 j 区 = 逻辑扇区 j；内环第 j 区 = 逻辑扇区 2j+1
    assert idx[zone(7, (21 + OFF) % 32).index] == 7 * 32 + 10
    assert idx[zone(0, (1 + OFF) % 32 // 2).index] == 0 * 32 + 0


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
