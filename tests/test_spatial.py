import math

import pytest

from soundmat.sonification.intent import Position
from soundmat.sound.spatial import PRESETS, SpeakerLayout, speaker_gains


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
    lay = PRESETS["stereo"]   # 左 330°，右 30°
    g = speaker_gains(Position(0.0, 1.0), lay)
    assert g[0] == pytest.approx(g[1]) == pytest.approx(math.sqrt(0.5))
    # 朝向偏移 30°：垫面 0° 对着右音箱
    g = speaker_gains(Position(0.0, 1.0), lay, orientation=30.0)
    assert g == pytest.approx([0.0, 1.0], abs=1e-9)


def test_single_speaker_and_json_roundtrip():
    lay = SpeakerLayout((0.0,))
    assert speaker_gains(Position(123, 1), lay) == [1.0]
    assert SpeakerLayout.from_json(PRESETS["quad"].to_json()) == PRESETS["quad"]
    with pytest.raises(ValueError):
        SpeakerLayout.from_json({"azimuths": []})
