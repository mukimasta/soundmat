import pytest

from soundmat.config import load_config


def test_repo_config_loads(config):
    assert config.mat.full_scale == 4095
    assert config.mat.occupancy_threshold == pytest.approx(245 / 4095)
    assert config.mat.inner_occupancy_threshold == pytest.approx(185 / 4095)
    assert config.mat.sector_offset == 4
    assert config.light.led_count == 108
    assert config.light.led_offset == 101
    assert config.sound.voice_budget_categories == {"melodic": 12}
    labels = [row["label"] for row in config.describe()]
    assert "去抖时间" in labels and "声部预算" in labels


def test_unknown_key_rejected(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("[mat]\noccupancy_treshold = 3\n")
    with pytest.raises(ValueError, match="occupancy_treshold"):
        load_config(p)


def test_unknown_section_rejected(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("[matt]\n")
    with pytest.raises(ValueError, match="matt"):
        load_config(p)
