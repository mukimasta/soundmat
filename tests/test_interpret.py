import numpy as np
import pytest

from soundmat.perception.interpret import Interpreter
from soundmat.perception.model import PressureMap
from soundmat.perception.zones import NUM_ZONES, ring_indices, zone

TH = 0.12


def pmap(t, on=(), value=0.5, seq=0):
    v = np.zeros(NUM_ZONES, dtype=np.float32)
    for i in on:
        v[i] = value
    return PressureMap(t=t, seq=seq, values=v)


def run(interp, frames):
    out = []
    for f in frames:
        _, ev, _ = interp.update(f)
        out.extend(ev)
    return out


def test_place_needs_stable_occupy_hold():
    it = Interpreter(TH, occupy_hold=0.04, release_hold=0.08)
    z = zone(3, 5).index
    assert run(it, [pmap(0.00, [z]), pmap(0.02, [z])]) == []
    ev = run(it, [pmap(0.04, [z])])
    assert [(e.kind, e.zone, e.t) for e in ev] == [("place", z, 0.04)]
    state, _, _ = it.update(pmap(0.05, [z]))
    assert state.occupied == {z}
    assert state.ring_counts[3] == 1


def test_short_blip_is_ignored():
    it = Interpreter(TH, 0.04, 0.08)
    z = zone(4, 0).index
    ev = run(it, [pmap(0.00, [z]), pmap(0.02), pmap(0.04, [z]), pmap(0.06)])
    assert ev == []


def test_lift_needs_stable_release_hold_and_dropouts_do_not_lift():
    it = Interpreter(TH, 0.0, 0.08)
    z = zone(2, 1).index
    assert [e.kind for e in run(it, [pmap(0.0, [z])])] == ["place"]
    # 短暂掉到阈值以下（读数闪断）不算拿起
    assert run(it, [pmap(0.02), pmap(0.05), pmap(0.07, [z]), pmap(0.2, [z])]) == []
    ev = run(it, [pmap(0.3), pmap(0.35), pmap(0.38)])
    assert [(e.kind, e.t) for e in ev] == [("lift", 0.38)]


def test_zero_hold_is_immediate():
    it = Interpreter(TH, 0.0, 0.0)
    z = 7
    assert [e.kind for e in run(it, [pmap(0, [z]), pmap(0.01)])] == ["place", "lift"]


def test_threshold_boundary():
    it = Interpreter(TH, 0.0, 0.0)
    state, ev, _ = it.update(pmap(0, [1], value=TH - 0.001))
    assert ev == [] and state.occupied == frozenset()
    state, ev, _ = it.update(pmap(0.01, [1], value=TH))
    assert [e.kind for e in ev] == ["place"]


def test_control_pressure_only_when_declared():
    it = Interpreter(TH, 0.0, 0.0)
    inner = [i for r in (0, 1) for i in ring_indices(r)]
    state, _, _ = it.update(pmap(0, inner[:3], value=0.05))
    assert state.control_pressure is None
    it.set_control_zones(set(inner))
    state, _, _ = it.update(pmap(0.01, inner[:3] + [zone(5, 0).index], value=0.05))
    # 控制区压力是控制区内压力之和，包括低于占用阈值的读数
    assert state.control_pressure == pytest.approx(0.15)


def test_features_are_pluggable():
    class Total:
        name = "total"

        def compute(self, pressure, state):
            return float(pressure.values.sum())

    it = Interpreter(TH, 0, 0)
    it.extractors.append(Total())
    _, _, feats = it.update(pmap(0, [1, 2], value=0.5))
    assert feats == {"total": pytest.approx(1.0)}


def test_release_threshold_is_lower_than_place():
    """双阈值：放下要过高线，拿起要低于低线，读数在两线之间保持原状。"""
    it = Interpreter(0.06, 0.0, 0.0, release_threshold=0.04)
    z = zone(4, 2).index
    assert run(it, [pmap(0.0, [z], value=0.05)]) == []                    # 没到放下阈值
    assert [e.kind for e in run(it, [pmap(0.1, [z], value=0.07)])] == ["place"]
    assert run(it, [pmap(0.2, [z], value=0.05)]) == []                    # 掉到两线之间：仍有石头
    assert [e.kind for e in run(it, [pmap(0.3, [z], value=0.03)])] == ["lift"]


def test_inner_rings_use_their_own_threshold(config):
    from soundmat.perception import Perception
    p = Perception(config.mat)
    th = p.interpreter.threshold
    assert th[zone(0, 3).index] == pytest.approx(185 / 4095)
    assert th[zone(5, 3).index] == pytest.approx(245 / 4095)
    assert p.interpreter.release_threshold[zone(5, 3).index] == pytest.approx(245 / 4095 * 0.67)
