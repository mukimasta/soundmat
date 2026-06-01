"""鼓引擎：曲式选段 + pattern 触发 + ghost 力度。"""
from soundmat import config
from soundmat.app import load_manifest
from soundmat.jam.config_loader import load_jam_config
from soundmat.jam.event import DrumEngine
from soundmat.jam.theory import Tempo


def _drum():
    cfg = load_jam_config(load_manifest(config.DEFAULT_MANIFEST))
    return DrumEngine(cfg.drum_patterns, cfg.drum_sequence, cfg.timing.bars_per_harmony_cycle)


def test_drum_form_sections():
    d = _drum()
    # 展开序列 A B C C A D D A，每段 8 小节（scheme 2）
    assert d.total_bars == 8 * 8
    assert d.loop_for_bar(0) == "A"    # 0-7
    assert d.loop_for_bar(8) == "B"    # 8-15
    assert d.loop_for_bar(16) == "C"   # 16-23
    assert d.loop_for_bar(24) == "C"
    assert d.loop_for_bar(32) == "A"
    assert d.loop_for_bar(40) == "D"


def test_drum_engine_form():
    d = _drum()
    tempo = Tempo(120)
    # 第 8 小节（section B）起点：B 的 kick[0]=1 + hihat[0]=1
    bar8_start = 8 * tempo.sec_per_bar
    events = d.emit(bar8_start - 0.001, bar8_start + tempo.sec_per_sixteenth * 0.5, tempo)
    voices = {e.voice for e in events}
    assert "kick" in voices and "hihat" in voices

    # section A（第 0 小节）应全静默
    a_events = d.emit(-0.001, tempo.sec_per_bar - 0.001, tempo)
    assert a_events == []


def test_ghost_velocity():
    d = _drum()
    tempo = Tempo(120)
    # D 段（bar 40+）含 ghost。扫第 40 小节整段，应出现 ghost 力度 0.38
    base = 40 * tempo.sec_per_bar
    events = d.emit(base - 0.001, base + tempo.sec_per_bar, tempo)
    vels = {round(e.velocity, 2) for e in events}
    assert 0.38 in vels
