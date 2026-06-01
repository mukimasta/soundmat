"""音乐理论层：数字记谱解析 + 移调 + 和弦 voicing 频率。"""
import math

from soundmat.jam.theory import DegreeParser, Tonality


def approx(a, b, tol=0.5):
    return abs(a - b) < tol


def test_degree_parse_basic():
    p = DegreeParser.parse("1")
    assert p.degree == 1 and p.accidental == 0 and p.octave == 4
    p = DegreeParser.parse("1#^")
    assert p.degree == 1 and p.accidental == 1 and p.octave == 5
    p = DegreeParser.parse("6__")
    assert p.degree == 6 and p.octave == 2
    p = DegreeParser.parse("4b_")
    assert p.degree == 4 and p.accidental == -1 and p.octave == 3
    assert DegreeParser.parse(None) is None
    assert DegreeParser.parse("null") is None
    assert DegreeParser.parse("8") is None


def test_tonality_c_major_anchor():
    t = Tonality("C", "major")
    assert t.midi("1") == 60          # C4
    assert approx(t.freq("1"), 261.63)
    assert t.midi("1^") == 72         # C5
    assert t.midi("5") == 67          # G4
    assert t.midi("6__") == 45        # A2
    assert approx(t.freq("6__"), 110.0)


def test_tonality_key_shift_nearest():
    # 设计文档：1^ 在 C 调是 C5，key 改 B 后变 B4（移到最近的根音，下方 1 个半音）
    c = Tonality("C", "major")
    b = Tonality("B", "major")
    assert c.midi("1^") == 72         # C5
    assert b.midi("1^") == 71         # B4


def test_chord_voicing_freqs_match_reference():
    # 进行 1 的 voicing（首调级数）应得到 web demo 的 C 调和弦频率
    t = Tonality("C", "major")
    voicing_2m9 = ["2_", "4_", "6_", "1", "3"]
    expected = [146.83, 174.61, 220.0, 261.63, 329.63]
    got = t.freqs(voicing_2m9)
    assert len(got) == 5
    for g, e in zip(got, expected):
        assert approx(g, e, 1.0)
