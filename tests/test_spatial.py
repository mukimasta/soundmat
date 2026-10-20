import math

import pytest

from soundmat.intent import Position
from soundmat.sound.spatial import PRESETS, SpeakerLayout, speaker_gains, voice_gains


def power(g):
    return sum(x * x for x in g)


@pytest.mark.parametrize("kind", ["stereo", "quad", "octo"])
def test_equal_power_everywhere(kind):
    lay = PRESETS[kind]
    for a in range(0, 360, 7):
        for r in (0.0, 0.3, 1.0):
            assert power(speaker_gains(Position(a, r), lay)) == pytest.approx(1.0)
    assert power(speaker_gains(None, lay)) == pytest.approx(1.0)


def test_outer_position_concentrates_on_nearest_speaker():
    lay = PRESETS["quad"]
    g = speaker_gains(Position(45.0, 1.0), lay)   # 正对右前音箱
    assert g[1] == pytest.approx(1.0)
    assert sum(g) == pytest.approx(1.0)


def test_center_is_uniform_and_unpositioned_is_uniform():
    lay = PRESETS["quad"]
    assert speaker_gains(Position(45.0, 0.0), lay) == pytest.approx([0.5] * 4)
    assert speaker_gains(None, lay) == pytest.approx([0.5] * 4)


def test_between_two_speakers_and_orientation():
    lay = PRESETS["stereo"]   # 左 270°，右 90°
    g = speaker_gains(Position(0.0, 1.0), lay)
    assert g[0] == pytest.approx(g[1]) == pytest.approx(math.sqrt(0.5))
    assert speaker_gains(Position(180.0, 1.0), lay) == pytest.approx(g)                     # 6 点也在正中
    assert speaker_gains(Position(90.0, 1.0), lay) == pytest.approx([0.0, 1.0], abs=1e-9)  # 3 点完全在右
    # 朝向偏移 90°：垫面 0° 对着右音箱
    g = speaker_gains(Position(0.0, 1.0), lay, orientation=90.0)
    assert g == pytest.approx([0.0, 1.0], abs=1e-9)


def test_unpositioned_stereo_source_keeps_its_channels():
    g = voice_gains(None, PRESETS["stereo"])
    assert g.left == pytest.approx([1.0, 0.0], abs=1e-9)
    assert g.right == pytest.approx([0.0, 1.0], abs=1e-9)
    g = voice_gains(None, PRESETS["octo"])           # 多只音箱：左前、右前
    assert g.left == pytest.approx(speaker_gains(Position(330.0, 1.0), PRESETS["octo"]))


def test_single_speaker_and_json_roundtrip():
    lay = SpeakerLayout((0.0,))
    assert speaker_gains(Position(123, 1), lay) == [1.0]
    assert SpeakerLayout.from_json(PRESETS["quad"].to_json()) == PRESETS["quad"]
    with pytest.raises(ValueError):
        SpeakerLayout.from_json({"azimuths": []})
