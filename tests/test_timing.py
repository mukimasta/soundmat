"""调度层：时间方案、扇区合并、扇区→表映射、扫描角。"""
import math

from soundmat.jam.scheduler.timing import SWEEP_START_ANGLE, Timing


def test_scheme2_one_revolution_two_bars():
    t = Timing(2)
    assert t.is_two_bar
    assert t.bars_per_harmony_cycle == 8
    # 120 BPM scheme 2：stepsPerSec = 120/15 = 8 sector/s；一圈 32 sector = 4 s
    assert t.steps_per_sec(120) == 8.0
    # 4 秒后扫描角回到起点附近（一整圈）
    a4 = t.sweep_angle_at(4.0, 120)
    assert approx_angle(a4, SWEEP_START_ANGLE)


def test_melody_trigger_sector_merge():
    t = Timing(2)
    # 两小节方案触发环：相邻 2 物理 sector 合并到偶数
    assert t.melody_trigger_sector(0, True) == 0
    assert t.melody_trigger_sector(1, True) == 0
    assert t.melody_trigger_sector(2, True) == 2
    assert t.melody_trigger_sector(3, True) == 2
    assert t.melody_trigger_sector(17, True) == 16
    # 非触发环不合并
    assert t.melody_trigger_sector(3, False) == 3


def test_map_to_table_sector_scheme2():
    t = Timing(2)
    # loop_rotation 决定和弦：rotation r → chord r（每圈一个和弦，4 圈一进行）
    for rot in range(4):
        pos = t.resolve_position(0, rot)
        assert pos["chord_index"] == rot
        assert pos["eighth_in_bar"] == 0
    # sector 16（第二小节起点）八分位也是 0（与第一小节同表）
    pos = t.resolve_position(16, 0)
    assert pos["chord_index"] == 0 and pos["eighth_in_bar"] == 0
    # sector 4 → 八分位 2
    assert t.resolve_position(4, 0)["eighth_in_bar"] == 2


def approx_angle(a, b, tol=0.05):
    d = abs((a - b) % (2 * math.pi))
    return d < tol or abs(d - 2 * math.pi) < tol
