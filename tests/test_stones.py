"""石头跟踪：按 2026-10-20 真垫子上看到的几种情况造压力序列（控制器约 30 帧/秒）。"""
import numpy as np
import pytest

from soundmat.config import MatConfig
from soundmat.perception import tracker_params
from soundmat.perception.interpret import Interpreter
from soundmat.perception.interpret.stones import NEIGHBOURS, StoneTracker
from soundmat.perception.model import PressureMap
from soundmat.perception.signal import zone_wire_index
from soundmat.perception.zones import NUM_ZONES, zone

FPS = 30.0
OUT = 245 / 4095          # 外环放下阈值（归一化）
STRIP = zone_wire_index(True, 4) % 32


def tracker():
    return StoneTracker(tracker_params(MatConfig()))


def values(d):
    v = np.zeros(NUM_ZONES)
    for z, x in d.items():
        v[z] = x
    return v


class Run:
    """按固定帧率喂压力，记录事件。"""

    def __init__(self, tr=None):
        self.tr = tr or tracker()
        self.t = 0.0
        self.events = []

    def hold(self, seconds, d):
        v = values(d)
        for _ in range(max(1, round(seconds * FPS))):
            self.events += self.tr.update(self.t, v)
            self.t += 1 / FPS
        return self

    def ramp(self, seconds, a, b):
        """在 seconds 内从读数表 a 线性变到 b。"""
        n = max(1, round(seconds * FPS))
        keys = set(a) | set(b)
        for i in range(1, n + 1):
            f = i / n
            self.events += self.tr.update(self.t, values({z: a.get(z, 0) * (1 - f) + b.get(z, 0) * f for z in keys}))
            self.t += 1 / FPS
        return self

    def kinds(self):
        return [e.kind for e in self.events]


A = zone(4, 10).index
B = zone(4, 11).index            # 同环相邻
C = zone(5, 10).index            # 外侧相邻（同一根扇区导电条）
FAR = zone(6, 25).index


def test_place_needs_strength_for_occupy_hold():
    r = Run().hold(0.05, {A: 0.2})
    assert r.events == []
    r.hold(0.06, {A: 0.2})
    assert [(e.kind, e.zone) for e in r.events] == [("place", A)]
    (s,) = r.tr.stones
    assert s.zone == A and s.zones == {A} and s.strength == pytest.approx(0.2 / OUT)


def test_noise_does_not_place():
    r = Run()
    for _ in range(20):                                  # 单帧跳动到 0.07，中间是 0.03 的底噪
        r.hold(1 / FPS, {A: 0.07}).hold(0.1, {A: 0.03})
    r.hold(1.0, {A: 0.03, B: 0.02})                      # 一直有一点底噪，加起来不到一个阈值
    assert r.events == [] and r.tr.stones == ()


def test_straddling_stone_is_one_stone():
    """骑在分界线上：两边各 98、99（千分之一满量程），单看都不到阈值，加起来是一颗石头。"""
    r = Run().hold(0.2, {A: 0.098, B: 0.099})
    assert r.kinds() == ["place"]
    (s,) = r.tr.stones
    assert s.zone == B and s.zones == {A, B}
    # 位置在两个区之间
    za, zb = zone(4, 10), zone(4, 11)
    assert za.center_deg < s.angle < zb.center_deg


def test_light_straddling_stone_below_threshold_on_both_sides():
    """更轻的一颗骑在线上：两边 45 和 42，都低于阈值 60（左右两个区在不同的导电条上，没有串扰补偿）。"""
    assert STRIP[A] != STRIP[B]
    r = Run().hold(1.5, {A: 0.045, B: 0.042})
    assert r.kinds() == ["place"]
    (s,) = r.tr.stones
    assert s.zone == A and s.zones == {A, B}


def test_radial_straddle_is_boosted_by_compensation():
    """内外骑线（同一根导电条）：两边互相拉低，补偿把弱的那边也算进来。"""
    r = Run().hold(1.0, {A: 0.071, C: 0.022})
    (s,) = r.tr.stones
    assert s.zones == {A, C}


def test_second_stone_next_to_the_first_is_split_off():
    r = Run().hold(1.0, {A: 0.2})
    r.ramp(0.1, {A: 0.2}, {A: 0.2, B: 0.15}).hold(0.3, {A: 0.2, B: 0.15})
    assert [e.kind for e in r.events] == ["place", "place"]
    assert {s.zone for s in r.tr.stones} == {A, B}
    assert len({e.stone for e in r.events}) == 2


def test_sliding_to_the_next_zone_is_a_move():
    r = Run().hold(1.0, {A: 0.2})
    r.ramp(0.3, {A: 0.2}, {A: 0.0, B: 0.2}).hold(0.5, {B: 0.2})
    assert r.kinds() == ["place", "move"]
    mv = r.events[1]
    assert (mv.from_zone, mv.zone) == (A, B) and mv.stone == r.events[0].stone
    assert [s.zone for s in r.tr.stones] == [B]


def test_dragging_across_a_ring_boundary_with_a_gap_is_a_move():
    """拖过环与环之间的缝：压力一帧帧掉下去，两三帧两边都读不到，再从外侧那一环出现。"""
    r = Run().hold(1.0, {A: 0.3})
    r.ramp(0.2, {A: 0.3}, {A: 0.05}).hold(0.15, {}).ramp(0.15, {}, {C: 0.3}).hold(0.5, {C: 0.3})
    assert r.kinds() == ["place", "move"]
    assert r.events[1].zone == C


def test_lift_is_quick_for_a_resting_stone():
    r = Run().hold(2.0, {A: 0.3})
    t_lift = r.t
    r.hold(0.3, {})
    (lift,) = [e for e in r.events if e.kind == "lift"]
    assert lift.t - t_lift <= 0.12 and lift.zone == A


def test_lift_waits_longer_right_after_moving():
    r = Run().hold(1.0, {A: 0.3}).ramp(0.2, {A: 0.3}, {B: 0.3}).hold(0.1, {B: 0.3})
    t_lift = r.t
    r.hold(0.6, {})
    (lift,) = [e for e in r.events if e.kind == "lift"]
    assert 0.35 <= lift.t - t_lift <= 0.46


def test_crosstalk_does_not_lift_a_stone():
    """同一根导电条上压了一个重的，轻的那颗读数被拉到 0.3 倍，低于压到的门槛，仍然在。"""
    assert STRIP[A] == STRIP[C]
    far = zone(7, 10).index
    assert STRIP[far] == STRIP[A]
    r = Run().hold(1.0, {A: 0.06})
    r.hold(0.05, {A: 0.06, far: 0.2}).hold(2.0, {A: 0.018, far: 0.4})
    assert r.kinds() == ["place", "place"]
    assert {s.zone for s in r.tr.stones} == {A, far}


def test_crosstalk_compensation_does_not_invent_stones():
    """补偿只给已有的石头：同一根条上有重石头时，别处的底噪不会被放大成石头。"""
    far = zone(7, 10).index
    r = Run().hold(2.0, {far: 0.4, A: 0.03})
    assert r.kinds() == ["place"]
    assert [s.zone for s in r.tr.stones] == [far]


def test_stones_on_different_strips_do_not_interact():
    r = Run().hold(1.0, {A: 0.2, FAR: 0.2})
    assert r.kinds() == ["place", "place"]
    r.hold(0.5, {FAR: 0.2})
    assert r.kinds() == ["place", "place", "lift"]


def test_touching_stones_stay_two_and_lift_separately():
    r = Run().hold(1.0, {A: 0.2})
    r.hold(0.4, {A: 0.2, B: 0.2})
    assert len(r.tr.stones) == 2
    r.hold(1.0, {B: 0.2})
    assert r.kinds() == ["place", "place", "lift"]
    assert [s.zone for s in r.tr.stones] == [B]


def test_large_object_is_one_stone():
    blob = {A: 0.3, B: 0.3, C: 0.3, zone(5, 11).index: 0.3, zone(4, 9).index: 0.2}
    r = Run().hold(0.5, blob)
    assert r.kinds() == ["place"]
    (s,) = r.tr.stones
    assert len(s.zones) == 5


def test_anchor_does_not_flicker_on_a_straddle():
    """骑线的石头两边读数交替略大一点，主区不来回换。"""
    r = Run().hold(0.3, {A: 0.1, B: 0.09})
    for _ in range(20):
        r.hold(0.1, {A: 0.095, B: 0.1}).hold(0.1, {A: 0.1, B: 0.095})
    assert r.kinds() == ["place"]


def test_neighbour_table_is_symmetric():
    for i, ns in enumerate(NEIGHBOURS):
        for j in ns:
            assert i in NEIGHBOURS[j]
    assert set(NEIGHBOURS[A]) >= {B, C, zone(4, 9).index, zone(3, 10).index}


# ── 垫面解读：状态与静下来 ───────────────────────────────────────────────

def interp():
    return Interpreter(tracker_params(MatConfig()), settle=3.0)


def test_state_counts_each_stone_once():
    it = interp()
    for i in range(10):
        state, _, _ = it.update(PressureMap(t=i / FPS, seq=i, values=values({A: 0.1, B: 0.1}).astype(np.float32)))
    assert state.occupied == {A} or state.occupied == {B}
    assert sum(state.ring_counts) == 1 and len(state.stones) == 1


def test_settle_once_after_activity():
    it = interp()
    kinds = []
    t = 0.0
    for d, secs in [({A: 0.2}, 1.0), ({A: 0.2}, 3.5), ({A: 0.2, FAR: 0.2}, 0.5), ({A: 0.2, FAR: 0.2}, 3.5)]:
        for _ in range(round(secs * FPS)):
            _, ev, _ = it.update(PressureMap(t=t, seq=0, values=values(d).astype(np.float32)))
            kinds += [(e.kind, round(e.t, 1)) for e in ev]
            t += 1 / FPS
    assert [k for k, _ in kinds] == ["place", "settle", "place", "settle"]
    assert kinds[1][1] == pytest.approx(kinds[0][1] + 3.0, abs=0.05)


# ── 从 10-18、10-20 的录音里看到的情况 ───────────────────────────────────

def test_slow_slide_is_a_move_not_a_second_stone():
    """慢慢滑到旁边：新区先升起来、旧区过一会儿才让出来，总压力大致不变（10-20 绕内环，1:13 → 1:12）。"""
    a, b = zone(1, 13).index, zone(1, 12).index
    r = Run().hold(1.0, {a: 0.204})
    # 旧区还保持在平时的八成以上，新区已经过了阈值：只有总压力没有多出一颗石头，说明是同一颗在滑
    r.ramp(0.3, {a: 0.204}, {a: 0.17, b: 0.05}).hold(0.3, {a: 0.17, b: 0.05})
    r.ramp(0.3, {a: 0.17, b: 0.05}, {b: 0.17}).hold(0.5, {b: 0.17})
    assert r.kinds() == ["place", "move"]
    assert [s.zone for s in r.tr.stones] == [b]


def test_crossing_the_centre_is_a_move():
    """最内环没有电极的圆心：从一边滑进去，过一会儿从对面出来，还是同一颗石头。"""
    w, e = zone(0, 12).index, zone(0, 4).index
    r = Run().hold(1.0, {w: 0.2})
    r.ramp(0.3, {w: 0.2}, {w: 0.03}).hold(0.5, {}).ramp(0.2, {}, {e: 0.2}).hold(0.5, {e: 0.2})
    assert r.kinds() == ["place", "move"]
    assert r.events[1].zone == e


def test_lost_stone_does_not_take_pressure_that_was_already_there():
    """拿起之后，附近早就有的一块压力（还不够一颗石头）不归它。"""
    a, near = zone(6, 3).index, zone(4, 3).index
    r = Run().hold(1.0, {a: 0.2, near: 0.03})
    r.hold(0.03, {a: 0.0, near: 0.03}).hold(0.3, {near: 0.065})
    assert r.kinds() == ["place", "lift", "place"]


def test_lost_stone_ignores_a_light_touch():
    a, near = zone(6, 3).index, zone(5, 4).index
    r = Run().hold(1.0, {a: 0.4})
    # 手碰了一下：过了压到的门槛，但远不到这颗石头平时的压力，也不够一颗石头
    r.ramp(0.2, {a: 0.4}, {a: 0.05}).hold(0.05, {}).hold(0.6, {near: 0.035})
    assert r.kinds() == ["place", "lift"]


def test_alternating_readings_do_not_report_moves():
    """两个区的读数一帧一帧交替（石头在手里晃）：主区不跟着来回换。"""
    r = Run().hold(0.5, {A: 0.15})
    for _ in range(30):
        r.hold(1 / FPS, {A: 0.15, B: 0.05}).hold(1 / FPS, {A: 0.05, B: 0.15})
    assert r.kinds() == ["place"]


def test_long_continuous_slide_stays_one_stone():
    """沿一环连续滑过 30 多个区，途中经过另一颗静止石头所在的导电条：始终是同一颗（曾经滑几个区后不停分出新石头）。"""
    ring = [zone(5, j).index for j in range(32)]
    still = zone(2, 6).index                       # 和 5:6 在同一根导电条上
    r = Run()
    t0 = r.t
    while r.t - t0 < 15.0:
        pos = ((r.t - t0) / 0.45) % 32
        j = int(pos)
        f = pos - j
        r.hold(1 / FPS, {ring[j]: 0.30 * (1 - f) + 0.05 * f, ring[(j + 1) % 32]: 0.30 * f + 0.05 * (1 - f), still: 0.25})
    places = [e for e in r.events if e.kind == "place"]
    assert len(places) == 2 and not [e for e in r.events if e.kind == "lift"]
    slider = next(e.stone for e in places if e.zone != still)
    assert len([e for e in r.events if e.kind == "move" and e.stone == slider]) >= 30


def test_virtual_mat_has_no_crosstalk_compensation(config):
    from soundmat.perception import Perception
    assert Perception(config.mat, source="virtual").interpreter.tracker.p.crosstalk == 0.0
    assert Perception(config.mat).interpreter.tracker.p.crosstalk == pytest.approx(7.0)
