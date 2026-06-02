import numpy as np

from soundmat import config
from soundmat.core.sensor.mock_reader import empty_matrix
from soundmat.core.sensor.normalize import normalize_wire_matrix


def test_mirror_reverses_columns():
    wire = empty_matrix()
    wire[3, 5] = 111
    wire[3, 26] = 222
    out = normalize_wire_matrix(wire, mirror=True)
    assert out[3, 26] == 111
    assert out[3, 5] == 222


def test_mirror_same_angle_inner_outer_share_wire_column():
    """同一物理角度（原 slice 0）镜像后内外圈落在同一 wire 列。"""
    wire = empty_matrix()
    wire[0, 0] = 100
    wire[7, 0] = 200
    out = normalize_wire_matrix(wire, mirror=True)
    assert out[0, 31] == 100
    assert out[7, 31] == 200


def test_mirror_inner_reads_odd_slice_after_reverse():
    from soundmat.core.sensor.map import wire_to_logical_adc

    wire = empty_matrix()
    wire[0, 0] = 400
    mirrored = normalize_wire_matrix(wire, mirror=True)
    config.WIRE_SLICE_MIRROR = True
    logical = wire_to_logical_adc(mirrored)
    off = config.SECTOR_OFFSET % config.NUM_SLICES
    assert logical[0, (1 + off) % config.NUM_SLICES] == 400


def test_mirror_inner_outer_pre_aligned():
    """镜像后同物理角度（原 slice 0）→ 同一 wire 列；内圈 pre[1]、外圈 pre[31]。"""
    from soundmat.core.sensor.map import _pre_offset_row

    wire = empty_matrix()
    wire[0, 0] = 100
    wire[7, 0] = 200
    mirrored = normalize_wire_matrix(wire, mirror=True)
    config.WIRE_SLICE_MIRROR = True
    pre_in = _pre_offset_row(0, mirrored[0])
    pre_out = _pre_offset_row(7, mirrored[7])
    assert mirrored[0, 31] == 100
    assert mirrored[7, 31] == 200
    assert pre_in[1] == 100
    assert pre_out[31] == 200


def test_mirror_disabled_is_copy():
    wire = empty_matrix()
    wire[0, 1] = 99
    out = normalize_wire_matrix(wire, mirror=False)
    assert out[0, 1] == 99
    assert out is not wire


def test_reader_emit_applies_mirror():
    from soundmat.core.sensor.mock_reader import MockSensorReader

    config.WIRE_SLICE_MIRROR = True
    reader = MockSensorReader()
    wire = empty_matrix()
    wire[7, 4] = 500
    reader._emit(wire)
    latest = reader.latest()
    assert latest is not None
    assert latest.matrix[7, 27] == 500
