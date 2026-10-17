"""移植自第一版 test_theory.py / test_timing.py。"""
import pytest

from soundmat.sonification.jam.theory import Tempo, Tonality, parse_degree, valid_token
from soundmat.sonification.jam.timing import Timing


def test_degree_parse():
    p = parse_degree("1#^")
    assert (p.degree, p.accidental, p.octave) == (1, 1, 5)
    assert parse_degree("6__").octave == 2
    p = parse_degree("4b_")
    assert (p.accidental, p.octave) == (-1, 3)
    assert parse_degree(None) is None and parse_degree("null") is None and parse_degree("8") is None
    assert valid_token("null") and not valid_token("9")


def test_tonality():
    t = Tonality("C", "major")
    assert t.midi("1") == 60 and t.midi("1^") == 72 and t.midi("6__") == 45
    assert t.freq("6__") == pytest.approx(110.0)
    assert Tonality("B", "major").midi("1^") == 71    # 移到最近的根音
    got = t.freqs(["2_", "4_", "6_", "1", "3"])
    assert got == pytest.approx([146.83, 174.61, 220.0, 261.63, 329.63], abs=0.01)
    with pytest.raises(ValueError):
        Tonality("H")


def test_tempo_sixteenths_half_open():
    tp = Tempo(120)
    assert tp.sixteenth == 0.125 and tp.bar == 2.0
    assert list(tp.sixteenths_in(0.0, 0.25)) == [0, 1]
    assert list(tp.sixteenths_in(0.25, 0.3)) == [2]
    assert list(tp.sixteenths_in(0.3, 0.3)) == []


def test_scheme2_geometry():
    t = Timing(2)
    assert t.steps_per_sec(120) == 8.0          # 一圈 32 扇区 = 4 秒 = 2 小节
    assert [t.trigger_sector(s) for s in (0, 1, 2, 3, 17)] == [0, 0, 2, 2, 16]
    for rot in range(4):
        assert t.resolve(0, rot) == (rot, 0)
    assert t.resolve(16, 0) == (0, 0) and t.resolve(4, 0) == (0, 2)
    assert Timing(3).resolve(16, 0) == (1, 0)


def test_hits_exact_times_half_open():
    t = Timing(2)
    hits = t.hits_in(0.0, 4.5, 120, [0, 8])
    assert hits == [(0.0, 0, 0), (1.0, 8, 0), (4.0, 0, 1)]
    assert t.hits_in(1.0, 1.0, 120, [8]) == []
    assert t.hits_in(0.999, 1.001, 120, [8]) == [(1.0, 8, 0)]
