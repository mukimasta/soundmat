import numpy as np
import pytest

from soundmat.clock import Beat
from soundmat.perception.model import MatEvent, MatSnapshot, MatState, PressureMap
from soundmat.perception.zones import NUM_ZONES, ZONES, zone
from soundmat.sonification.arrangements import ARRANGEMENTS_DIR, load_arrangement
from soundmat.sonification.jam import JamMode
from soundmat.sonification.mode import ModeContext

DT = 1 / 60
START = 250 / 4095


def snap(t, zones=(), control=0.0):
    counts = [0] * 8
    for z in zones:
        counts[ZONES[z].ring] += 1
    return MatSnapshot(PressureMap(t, 0, np.zeros(NUM_ZONES, dtype=np.float32)),
                       MatState(t, frozenset(zones), tuple(counts), control))


def jam():
    m = JamMode(load_arrangement(ARRANGEMENTS_DIR / "lofi_1"), ModeContext(led_count=108))
    m.plan = m.load()
    m.start(0.0)
    return m


def run(m, t0, t1, zones=(), control=0.0, events=None):
    """从 t0 到 t1 每拍调用一次，返回 (全部事件, 最后一拍的输出)。"""
    out_events, out = [], None
    i, t = 0, t0
    while t < t1 - 1e-9:
        out = m.tick(Beat(i, t, DT), snap(t, zones, control), (events or {}).pop(round(t, 6), []) if events else [])
        out_events += out.sound.events
        i += 1
        t = t0 + i * DT
    return out_events, out


def test_plan():
    m = jam()
    p = m.plan
    assert p.lookahead == 0.1
    assert p.buses[-2:] == ("harmony", "drums")
    assert len(p.control_zones) == 32 and all(ZONES[z].ring in (0, 1) for z in p.control_zones)
    assert "jam_marimba" in p.instruments and "jam_chord_pad" in p.instruments
    assert m.total_bars == 64 and m.form_duration == pytest.approx(128.0)


def test_idle_until_control_pressure():
    m = jam()
    _, out = run(m, 0, 0.5, control=START * 0.5)
    assert out.status.transport == "idle" and out.status.text.startswith("空闲")
    assert out.sound.voices == ()


def test_start_harmony_and_drums_on_grid():
    m = jam()
    evs, out = run(m, 10.0, 10.0 + 18.0, control=START * 2)   # 播到第 9 小节（B 段）
    assert out.status.transport == "playing"
    # 和声：当前小节一个声部，开始时刻正好在小节线上
    pads = [v for v in out.sound.voices if v.bus == "harmony"]
    assert pads and {p.id.rsplit(".", 1)[1] for p in pads} <= {"bar8", "bar9"}
    for p in pads:
        assert (p.start - 10.0) % 2.0 == pytest.approx(0.0, abs=1e-9)
    # A 段（前 8 小节，16 秒）没有鼓；B 段第一个 kick 正好在 16 秒
    kicks = sorted(e.time for e in evs if ".kick." in e.id)
    assert kicks[0] == pytest.approx(10.0 + 16.0)
    hats = sorted(e.time for e in evs if ".hihat." in e.id)
    assert np.allclose(np.diff(hats), 0.25)            # 八分 hihat
    assert len({e.id for e in evs}) == len(evs)        # 每个事件只交出一次
    assert out.status.text.startswith("第 2 段 B")


def test_next_bar_pad_appears_inside_lookahead_with_exact_start():
    m = jam()
    run(m, 0.0, 1.0, control=START * 2)
    # 第 1 小节线在 2.0 秒；1.95 的前瞻窗 [1.95, 2.05) 覆盖它
    out = m.tick(Beat(0, 1.95, DT), snap(1.95, (), START * 2), [])
    starts = sorted(v.start for v in out.sound.voices if v.bus == "harmony")
    assert starts == pytest.approx([0.0, 2.0])


def test_scan_hits_at_exact_times_with_table_pitch():
    m = jam()
    z7 = zone(7, 0).index           # 第 0 扇区：开始时刻命中
    z5 = zone(5, 9).index           # 第 9 扇区 → 合并到 8：1.0 秒命中
    evs, _ = run(m, 5.0, 6.5, zones=(z7, z5), control=START * 2)
    hits = sorted((e.time, e.bus, e.params["freq"]) for e in evs if ".scan." in e.id)
    assert hits[0][0] == pytest.approx(5.0) and hits[0][1] == "ring7"
    assert hits[0][2] == pytest.approx(659.26, abs=0.01)            # 2m9 第 7 环第 0 八分 = 3^ = E5
    assert hits[1][0] == pytest.approx(6.0) and hits[1][1] == "ring5"
    ev = next(e for e in evs if e.bus == "ring5")
    assert ev.category == "melodic" and ev.params["ringGain"] == 3.45 and ev.params["far"] == 1.0
    assert ev.position.angle == pytest.approx(ZONES[z5].center_deg)


def test_same_sector_group_shares_velocity():
    m = jam()
    zs = (zone(5, 0).index, zone(6, 0).index, zone(7, 1).index)
    evs, _ = run(m, 0.0, 0.2, zones=zs, control=START * 2)
    vels = [e.params["velocity"] for e in evs if ".scan." in e.id]
    assert len(vels) == 3 and vels == pytest.approx([1 / np.sqrt(3)] * 3)


def test_second_rotation_uses_next_chord():
    m = jam()
    z = zone(7, 0).index
    evs, _ = run(m, 0.0, 4.2, zones=(z,), control=START * 2)
    hits = sorted((e.time, e.params["freq"]) for e in evs if ".scan." in e.id)
    assert [round(t, 6) for t, _ in hits] == [0.0, 4.0]
    # 第二圈：513 第 7 环第 0 八分
    assert hits[1][1] == pytest.approx(m.tonality.freq(m.triggers["513"][7][0]))


def test_release_hold_then_reset_and_form_end():
    m = jam()
    run(m, 0, 1.0, control=START * 2)
    _, out = run(m, 1.0, 1.05, control=0.0)          # 少于 0.1 秒的闪断
    assert out.status.transport == "playing"
    _, out = run(m, 1.05, 1.3, control=0.0)
    assert out.status.transport == "idle"
    # 走完曲式进入曲终，持续压着也不重新开始
    run(m, 2.0, 2.0 + 128.2, control=START * 2)
    _, out = run(m, 130.3, 130.5, control=START * 2)
    assert out.status.transport == "ended" and out.sound.voices == ()
    _, out = run(m, 130.5, 130.8, control=0.0)
    assert out.status.transport == "idle"


def test_idle_preview_and_no_preview_while_playing():
    m = jam()
    z = zone(6, 4).index
    out = m.tick(Beat(0, 1.0, DT), snap(1.0, (z,)), [MatEvent("place", z, 1.0)])
    (ev,) = out.sound.events
    assert ev.time is None and ev.params["velocity"] == 0.5
    assert out.light.layers[0].alpha.max() > 0.9      # 预听的灯光闪烁
    run(m, 2.0, 2.5, control=START * 2)
    out = m.tick(Beat(0, 2.5, DT), snap(2.5, (z,), START * 2), [MatEvent("place", z, 2.5)])
    assert not [e for e in out.sound.events if ".preview." in e.id]


def test_lofi_maps_and_smooths():
    m = jam()
    out = m.tick(Beat(0, 0, DT), snap(0, (), 0.0), [])
    assert out.sound.globals["cutoff"] == 14000 and out.sound.globals["bus.harmony"] == 0.4
    # 压力和 8000（原始读数）→ Lo-Fi 1000，平滑逼近
    for i in range(1, 40):
        out = m.tick(Beat(i, i * DT, DT), snap(i * DT, (), 8000 / 4095), [])
    assert out.sound.globals["cutoff"] == pytest.approx(2425, abs=1)
    assert out.status.reading == "Lo-Fi 100%"


def test_lights_follow_what_is_heard():
    """扫描命中由声音引擎推后 heard_after 秒发声：命中灯光在那一刻亮。"""
    m = JamMode(load_arrangement(ARRANGEMENTS_DIR / "lofi_1"), ModeContext(led_count=108, heard_after=0.15))
    m.plan = m.load()
    m.start(0.0)
    z7 = zone(7, 0).index                                       # 第 0 扇区：开始时刻命中
    run(m, 5.0, 5.12, zones=(z7,), control=START * 2)
    assert [round(f[0], 3) for f in m.lights.flashes] == [5.15]
    _, out = run(m, 5.12, 5.2, zones=(z7,), control=START * 2)
    alpha = out.light.layers[0].alpha
    assert alpha.max() > 0                                        # 命中的闪光（5.15 起）已经亮了
