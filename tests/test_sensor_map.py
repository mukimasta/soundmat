"""S → L 坐标映射（设计文档 §13）。"""
from soundmat import config
from soundmat.core.sensor.map import wire_to_logical_adc
from soundmat.core.sensor.mock_reader import empty_matrix


def test_outer_identity_before_offset():
    wire = empty_matrix()
    wire[7, 10] = 2000
    logical = wire_to_logical_adc(wire)
    off = config.SECTOR_OFFSET % config.NUM_SLICES
    # pre[10]=2000 → logical[(10 + off) % 32]
    assert logical[7, (10 + off) % config.NUM_SLICES] == 2000
    assert logical[7, 10] == 0


def test_inner_even_slice_to_odd_sector_then_offset():
    wire = empty_matrix()
    wire[0, 0] = 3000   # even slice → pre sector 1
    wire[0, 2] = 2500   # → pre sector 3
    wire[0, 1] = 9999   # odd slice ignored
    logical = wire_to_logical_adc(wire)
    off = config.SECTOR_OFFSET % config.NUM_SLICES
    assert logical[0, (1 + off) % config.NUM_SLICES] == 3000
    assert logical[0, (3 + off) % config.NUM_SLICES] == 2500
    assert logical[0, 1] == 0      # pre[30] even, empty


def test_inner_offset_odd_swaps_parity():
    """offset 为奇数时，pre-offset 奇 sector 上的值会落到偶 sector。"""
    wire = empty_matrix()
    wire[1, 4] = 1800  # slice 4 → pre sector 5
    logical = wire_to_logical_adc(wire)
    off = config.SECTOR_OFFSET % config.NUM_SLICES
    assert logical[1, (5 + off) % config.NUM_SLICES] == 1800
