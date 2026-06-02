"""端到端（无 SC）：加载真实 manifest → 扫描命中石头 → 得到正确触发音。"""
import math

from soundmat import config
from soundmat.app import load_manifest
from soundmat.jam.config_loader import load_jam_config
from soundmat.jam.event import EventEngine
from soundmat.jam.scheduler import ScanLine, SongPositionTracker
from soundmat.jam.scheduler.timing import SWEEP_START_ANGLE, sector_center_angle
from soundmat.jam.theory import Tonality


def _build():
    manifest = load_manifest(config.DEFAULT_MANIFEST)
    cfg = load_jam_config(manifest)
    song = SongPositionTracker(cfg.progression, cfg.timing)
    engine = EventEngine(cfg.timing, cfg.rings, cfg.trigger_tables, song)
    tonality = Tonality(cfg.key, cfg.scale)
    return cfg, song, engine, tonality


def test_config_loads():
    cfg, *_ = _build()
    assert cfg.bpm == 120 and cfg.scheme == 2
    assert [c for c, _ in cfg.progression] == ["2m9", "513", "1maj9", "69"]
    assert cfg.rings[7].instrument == "jam_marimba"
    assert cfg.trigger_tables["2m9"][7][0] == "3^"
    assert cfg.drum_sequence == ["A", "B", "C", "C", "A", "D", "D", "A"]


def test_sweep_hit_r7_sector0_gives_3_up():
    cfg, song, engine, tonality = _build()
    # 扫过 sector 0 中心（-π/2），R7 sector0 有石 → 触发 2m9 R7 第 0 八分 = "3^"
    prev = SWEEP_START_ANGLE - 0.01
    curr = SWEEP_START_ANGLE + 0.01
    notes = engine.emit_sweep(
        prev, curr, did_wrap=False,
        occupied={(7, 0)}, now=1.0, loop_rotation=0, tonality=tonality,
    )
    assert len(notes) == 1
    assert notes[0].ring == 7
    assert notes[0].degree == "3^"
    assert notes[0].source_slice == 0


def test_retrigger_cooldown():
    cfg, song, engine, tonality = _build()
    prev, curr = SWEEP_START_ANGLE - 0.01, SWEEP_START_ANGLE + 0.01
    kw = dict(occupied={(7, 0)}, loop_rotation=0, tonality=tonality)
    n1 = engine.emit_sweep(prev, curr, False, now=1.0, **kw)
    n2 = engine.emit_sweep(prev, curr, False, now=1.05, **kw)  # 50ms 内
    assert len(n1) == 1 and len(n2) == 0


def test_mark_triggered_blocks_sweep():
    cfg, song, engine, tonality = _build()
    prev, curr = SWEEP_START_ANGLE - 0.01, SWEEP_START_ANGLE + 0.01
    engine.mark_triggered(7, 0, 1.0)
    notes = engine.emit_sweep(
        prev, curr, False, occupied={(7, 0)}, now=1.05, loop_rotation=0, tonality=tonality,
    )
    assert notes == []


def test_sqrt_velocity_grouping():
    cfg, song, engine, tonality = _build()
    prev, curr = SWEEP_START_ANGLE - 0.01, SWEEP_START_ANGLE + 0.01
    # R5/R6/R7 同 sector0 → 同合并扇区组，3 颗 → velocity ≈ 1/√3
    notes = engine.emit_sweep(
        prev, curr, False, occupied={(5, 0), (6, 0), (7, 0)},
        now=1.0, loop_rotation=0, tonality=tonality,
    )
    assert len(notes) == 3
    for n in notes:
        assert abs(n.velocity - 1 / math.sqrt(3)) < 0.01


def test_wrap_frame_sector0_uses_next_chord():
    """回绕帧 sector0 应在 rotation 0→1 边界查 513，而非 1maj9（bar 推导会 double-advance）。"""
    cfg, song, engine, tonality = _build()
    prev, curr = SWEEP_START_ANGLE - 0.01, SWEEP_START_ANGLE + 0.01
    notes = engine.emit_sweep(
        prev, curr, did_wrap=True,
        occupied={(4, 0)}, now=1.0, loop_rotation=0, tonality=tonality,
    )
    assert len(notes) == 1
    assert notes[0].degree == "2"  # 513 · R4 · 第 0 八分


def test_wrap_frame_sector16_stays_on_outgoing_chord():
    """回绕帧 sector16（第二小节起点）仍属 outgoing rotation 0 → 2m9。"""
    cfg, song, engine, tonality = _build()
    center = sector_center_angle(16)
    prev, curr = center - 0.01, center + 0.01
    notes = engine.emit_sweep(
        prev, curr, did_wrap=True,
        occupied={(4, 16)}, now=1.0, loop_rotation=0, tonality=tonality,
    )
    assert len(notes) == 1
    assert notes[0].degree == "4"  # 2m9 · R4 · 第 0 八分
