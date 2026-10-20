import numpy as np
import pytest

from soundmat.config import MatConfig
from soundmat.perception import Perception, tracker_params
from soundmat.perception.interpret import Interpreter
from soundmat.perception.model import PressureMap
from soundmat.perception.zones import NUM_ZONES, ring_indices, zone


def pmap(t, on=(), value=0.5, seq=0):
    v = np.zeros(NUM_ZONES, dtype=np.float32)
    for i in on:
        v[i] = value
    return PressureMap(t=t, seq=seq, values=v)


def interp(**kw):
    return Interpreter(tracker_params(MatConfig(**kw)))


def run(it, frames):
    out = []
    for f in frames:
        _, ev, _ = it.update(f)
        out.extend(ev)
    return out


def test_place_then_state_and_ring_counts():
    it = interp()
    z = zone(3, 5).index
    assert run(it, [pmap(0.00, [z]), pmap(0.04, [z])]) == []
    ev = run(it, [pmap(0.08, [z])])
    assert [(e.kind, e.zone, e.t) for e in ev] == [("place", z, 0.08)]
    state, _, _ = it.update(pmap(0.09, [z]))
    assert state.occupied == {z} and state.ring_counts[3] == 1
    (s,) = state.stones
    assert s.zone == z and s.placed_at == 0.08


def test_zero_hold_is_immediate():
    it = interp(occupy_hold=0.0, release_hold=0.0)
    z = zone(2, 7).index
    assert [e.kind for e in run(it, [pmap(0, [z]), pmap(0.01)])] == ["place", "lift"]


def test_threshold_is_the_whole_stone_and_inner_rings_are_lower(config):
    p = Perception(config.mat)
    th = p.interpreter.tracker.threshold
    assert th[zone(0, 3).index] == pytest.approx(185 / 4095)
    assert th[zone(5, 3).index] == pytest.approx(245 / 4095)
    it = interp(occupy_hold=0.0)
    outer, inner = zone(5, 3).index, zone(1, 3).index
    state, ev, _ = it.update(pmap(0, [outer, inner], value=0.05))       # 外环不到 60，内环过了 45
    assert [e.zone for e in ev] == [inner]


def test_control_pressure_only_when_declared():
    it = interp(occupy_hold=0.0)
    inner = [i for r in (0, 1) for i in ring_indices(r)]
    state, _, _ = it.update(pmap(0, inner[:3], value=0.05))
    assert state.control_pressure is None
    it.set_control_zones(set(inner))
    state, _, _ = it.update(pmap(0.01, inner[:3] + [zone(5, 0).index], value=0.05))
    # 控制区压力是控制区内压力之和，包括低于阈值的读数
    assert state.control_pressure == pytest.approx(0.15)


def test_features_are_pluggable():
    class Total:
        name = "total"

        def compute(self, pressure, state):
            return float(pressure.values.sum())

    it = interp()
    it.extractors.append(Total())
    _, _, feats = it.update(pmap(0, [1, 2], value=0.5))
    assert feats == {"total": pytest.approx(1.0)}


def test_reset_forgets_stones():
    it = interp(occupy_hold=0.0)
    z = zone(4, 4).index
    run(it, [pmap(0, [z])])
    it.reset()
    state, ev, _ = it.update(pmap(0.01))
    assert ev == [] and state.stones == ()
