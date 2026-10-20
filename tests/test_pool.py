import math
from dataclasses import replace

import numpy as np
import pytest

from soundmat.clock import Beat
from soundmat.perception.model import MatEvent, MatSnapshot, MatState, PressureMap
from soundmat.perception.zones import NUM_ZONES, ZONES, zone
from soundmat.sonification.arrangements import ARRANGEMENTS_DIR, load_arrangement
from soundmat.sonification.mode import Arrangement, LoadError, ModeContext
from soundmat.sonification.pool import INSTRUMENTS, KEY_SEMITONES, PENTATONIC_C, PoolMode

CTX = ModeContext(led_count=108, seed=5)


def snap(t, zones):
    counts = [0] * 8
    for z in zones:
        counts[ZONES[z].ring] += 1
    return MatSnapshot(
        pressure=PressureMap(t, 0, np.zeros(NUM_ZONES, dtype=np.float32)),
        state=MatState(t, frozenset(zones), tuple(counts), None),
    )


def meditation(**content):
    arr = load_arrangement(ARRANGEMENTS_DIR / "meditation")
    if content:
        arr = Arrangement(id=arr.id, title=arr.title, mode=arr.mode, content={**arr.content, **content})
    m = PoolMode(arr, CTX)
    m.plan = m.load()
    m.start(0.0)
    return m


class Run:
    """按 60 拍/秒驱动模式；stones 是 {区域: (放下时刻, 拿起时刻或 None)}。"""

    def __init__(self, mode, stones=None):
        self.mode, self.stones, self.prev, self.i = mode, dict(stones or {}), set(), 0

    def until(self, t_end):
        outs = []
        while self.i / 60 <= t_end + 1e-9:
            t = self.i / 60
            occ = {z for z, (on, off) in self.stones.items() if on <= t and (off is None or t < off)}
            evs = [MatEvent("place", z, t) for z in sorted(occ - self.prev)]
            evs += [MatEvent("lift", z, t) for z in sorted(self.prev - occ)]
            self.prev = occ
            outs.append(self.mode.tick(Beat(self.i, t, 1 / 60), snap(t, occ), evs))
            self.i += 1
        return outs


def events(outs, name):
    return [e for o in outs for e in o.sound.events if f":{name}#" in e.id]


def test_meditation_plan():
    m = meditation()
    assert m.plan.instruments == INSTRUMENTS
    assert m.plan.buses == ("bed",) + tuple(f"ring{r}" for r in range(8))
    assert m.plan.fx == "sm_fx_pool" and m.plan.assets == frozenset()


@pytest.mark.parametrize("content, message", [
    ({"rings": ["pad"] * 8}, "两次"),
    ({"rings": ["low_drone"]}, "8 项"),
    ({"rings": ["low_drone", "mid_drone", "pad", "mid_notes", "high_notes", "weather", "bells", "rain"]}, "未知的层"),
    ({"music": {"key_dwell": [10]}}, "key_dwell"),
    ({"breath": {"period": 0}}, "breath.period"),
    ({"breath": {"sound_depth_db": -1}}, "sound_depth_db"),
    ({"light": {"color": [255, 196]}}, "light.color"),
    ({"light": {"color": [255, 196, 300]}}, "light.color"),
    ({"light": {"breath_max": 1.5}}, "breath_max"),
    ({"light": {"breath_min": 0.3, "breath_max": 0.2}}, "不能大于"),
    ({"light": {"stone_width": 1.5}}, "stone_width"),
    ({"light": {"brightness": 1}}, "未知"),
])
def test_load_errors(content, message):
    with pytest.raises(LoadError, match=message):
        meditation(**content)


def test_bed_plays_on_an_empty_mat_and_distant_notes_follow_its_volume():
    outs = Run(meditation()).until(40.0)
    assert all(any(v.id == "bed" and v.bus == "bed" for v in o.sound.voices) for o in outs)
    bed = outs[0].sound.voices[0]
    assert bed.params["t"] == 1.0 and bed.params["depth"] == 2.0
    distant = events(outs, "distant")
    assert 1 <= len(distant) <= 3                       # 每 15–30 秒一声
    d = distant[0]
    assert d.bus == "bed" and d.position is None
    expect = (2 * math.pi * d.time / 67) % (2 * math.pi)
    assert d.params["volPhase"] == pytest.approx(expect) and d.params["volHz"] == pytest.approx(1 / 67)
    assert outs[-1].status.text.startswith("五声 C 调 · ")


def test_drones_follow_stones_keep_pitch_per_zone_and_change_with_key():
    m = meditation()
    z = zone(0, 5)
    run = Run(m, {z.index: (0.5, 2.0)})
    out = run.until(1.0)[-1]
    (drone,) = [v for v in out.sound.voices if v.id.startswith("low_drone.")]
    assert drone.source.name == "pool_drone_tri" and drone.bus == "ring0"
    assert drone.params["freq"] in PENTATONIC_C[2]
    assert drone.position.angle == pytest.approx(z.center_deg)
    assert (drone.fade_in, drone.fade_out, drone.category) == (3.0, 1.5, "melodic")
    # 拿起（2 秒）再放下（3 秒）：同一个调里音高不变
    assert not [v for v in run.until(2.5)[-1].sound.voices if v.id.startswith("low_drone.")]
    run.stones[z.index] = (3.0, None)
    again = [v for v in run.until(3.5)[-1].sound.voices if v.id.startswith("low_drone.")][0]
    assert again.id == drone.id and again.params == drone.params
    # 换调：标识换代，音高取新调的五声
    m.key.next_change = 4.0
    out = run.until(4.1)[-1]
    (new,) = [v for v in out.sound.voices if v.id.startswith("low_drone.")]
    assert new.id != drone.id and m.key.index == 1
    factor = 2 ** (KEY_SEMITONES[1] / 12)
    assert new.params["freq"] in [pytest.approx(f * factor) for f in PENTATONIC_C[2]]
    assert out.status.text.startswith("五声 G 调")


def test_pads_start_a_note_at_once_and_then_every_interval():
    m = meditation()
    z = zone(2, 9)
    outs = Run(m, {z.index: (0.0, None)}).until(20.0)
    pads = [[v for v in o.sound.voices if v.id.startswith("pad.")][0] for o in outs]
    assert pads[0].params["n"] == 1.0 and pads[0].fade_in == 2.0 and pads[0].category == "melodic"
    changes = [(i / 60, p.params["n"]) for i, p in enumerate(pads) if i and p.params["n"] != pads[i - 1].params["n"]]
    interval = m.layers[2].pads[z.index]["interval"]
    assert 4 <= interval <= 8
    assert [n for _, n in changes] == [2.0, 3.0, 4.0][:len(changes)] and len(changes) >= 2
    assert changes[0][0] == pytest.approx(interval, abs=1 / 60)
    assert all(p.params["freq"] in PENTATONIC_C[4] for p in pads)


def test_bells_ring_when_placed_then_every_six_seconds():
    m = meditation()
    a, b = zone(6, 3), zone(6, 4)                          # 一颗石头压到相邻两个区域
    outs = Run(m, {a.index: (1.0, None), b.index: (1.05, None)}).until(14.0)
    bells = events(outs, "bells")
    assert bells[0].time is None and bells[0].position.angle == pytest.approx(a.center_deg)
    assert bells[0].source.name == "pool_bell" and 10 <= bells[0].params["decay"] <= 18
    assert len([e for e in bells if e.time is None]) == 1  # 0.3 秒内第二个放下不再立即响，节奏也不变
    later = [e.time for e in bells if e.time is not None]
    assert later and all(5.5 <= t2 - t1 <= 6.5 for t1, t2 in zip([1.0] + later, later))


def test_high_notes_echo_and_mid_notes_use_triangle():
    outs = Run(meditation(), {zone(3, 1).index: (0.0, None), zone(4, 1).index: (0.0, None)}).until(10.0)
    (mid, *_), (high, *_) = events(outs, "mid_notes"), events(outs, "high_notes")
    assert mid.source.name == "pool_note" and mid.params["tri"] == 1.0
    assert high.source.name == "pool_note_echo" and high.params["tri"] == 0.0


def test_weather_mix_follows_stone_count_and_three_to_four_brings_thunder():
    m = meditation()
    zs = [zone(5, k).index for k in (0, 6, 12, 18, 24)]
    stones = {z: (1.0 + i, None) for i, z in enumerate(zs[:4])}
    run = Run(m, stones)
    out = run.until(1.1)[-1]
    w = next(v for v in out.sound.voices if v.id == "weather")
    assert (w.params["windMix"], w.params["rain"]) == (1.0, 0.0) and w.position is None
    out = run.until(3.1)[-1]
    w = next(v for v in out.sound.voices if v.id == "weather")
    assert w.params["windMix"] == pytest.approx(1 / 3) and 0 < w.params["rain"] < 2 / 3     # 雨正在渐入
    outs = run.until(4.1)
    thunder = events(outs, "thunder")
    assert len(thunder) == 1 and thunder[0].time == pytest.approx(4.0, abs=0.02)
    w = next(v for v in outs[-1].sound.voices if v.id == "weather")
    assert w.params["windMix"] == 0.0 and w.params["rain"] < 1.0
    assert 1.5 <= w.params["boost"] <= 2.25                  # 雷声时雨声加强
    p = thunder[0].params
    out = run.until(4.0 + p["tAtk"] + p["sus"] + 0.05)[-1]
    w = next(v for v in out.sound.voices if v.id == "weather")
    assert w.params["boost"] == 1.0 and w.params["boostTime"] == pytest.approx(p["tRel"] + 0.6)


def test_nature_drop_on_placement_then_birds_and_drops():
    m = meditation()
    zs = [zone(7, k).index for k in (2, 9, 16, 23, 30)]
    outs = Run(m, {z: (1.0, None) for z in zs}).until(60.0)
    drops = events(outs, "drop")
    assert drops[0].time is None and drops[0].source.name == "pool_drop"
    assert len([d for d in drops if d.time is None]) == 1   # 同一拍放下五颗，只立即响一滴
    chirps = events(outs, "chirp")
    assert chirps and all(c.position is None and c.bus == "ring7" for c in chirps)
    assert all(0.06 <= c.params["decay"] for c in chirps)
    # 一问一答：后面几声和第一声在同一拍交出，带着之后的准确时刻
    ahead = [e.time - i / 60 for i, o in enumerate(outs) for e in o.sound.events if ":chirp#" in e.id]
    assert max(ahead) >= 0.5


def test_layers_react_only_to_their_own_ring():
    """网页上放任何一颗石头都会重建所有层；这里放在别的环不会让钟声提前响。"""
    m = meditation()
    bell = zone(6, 0).index
    run = Run(m, {bell: (0.0, None), zone(0, 4).index: (3.0, None), zone(5, 4).index: (3.2, None)})
    bells = [e for e in events(run.until(5.4), "bells")]
    assert len(bells) == 1                                 # 只有放下时那一声，下一声在 5.5–6.5 秒


def _brightness(out):
    """灯光层合成到黑底后每颗灯的亮度（0–1，取最亮的通道相对颜色的比例）。"""
    from soundmat.light import composite
    return composite(out.light.layers, 108).max(axis=1) / 255


def test_bed_volume_breath_is_sent_every_quarter_second():
    m = meditation()
    outs = Run(m).until(67.0)
    bed = [next(v for v in o.sound.voices if v.id == "bed").params["breath"] for o in outs]
    # ±2 dB 的起伏最高在四分之一周期（约 16.75 秒），最低在四分之三处
    assert abs(int(np.argmax(bed)) / 60 - 16.75) < 0.5 and abs(int(np.argmin(bed)) / 60 - 50.25) < 0.5
    # 底音拿到的值每 0.25 秒才变一次，是这一段结束时的呼吸值
    assert len({round(b, 9) for b in bed[:60]}) == 4
    assert bed[0] == pytest.approx(m.breath.value(0.25))


def test_light_follows_the_measured_bed_level():
    measured = {"bed": None}
    asked = []

    def report(key):
        asked.append(key)
        return measured.get(key)

    arr = load_arrangement(ARRANGEMENTS_DIR / "meditation")
    m = PoolMode(arr, replace(CTX, report=report))
    m.plan = m.load()
    m.start(0.0)
    run = Run(m)
    far = lambda out: float(out.light.layers[0].alpha[54])      # 底色层，6 点方向
    assert far(run.until(0.5)[-1]) == pytest.approx(0.05)         # 还没有测量值：停在中间
    for level, expect in ((0.0, 0.0), (1.0, 0.10), (0.3, 0.03), (1.7, 0.10)):
        measured["bed"] = [level]
        assert far(run.until(run.i / 60)[-1]) == pytest.approx(expect)
    measured["bed"] = None                                        # 偶尔收不到：沿用上一个值
    assert far(run.until(run.i / 60)[-1]) == pytest.approx(0.10)
    assert set(asked) == {"bed"}


def test_light_is_one_warm_color_and_stones_are_brighter():
    m = meditation()
    z = zone(6, 8)                                       # 3 点方向
    out = Run(m, {z.index: (0.0, None)}).until(1.0)[-1]
    from soundmat.light import composite
    rgb = composite(out.light.layers, 108).astype(float)
    lit = rgb[rgb.max(axis=1) > 0]
    # 每颗灯都是同一种颜色，只是明暗不同（允许取整误差）
    assert (lit == lit[:, :1]).all()                   # 三个通道相等
    b = _brightness(out)
    assert b[27] > 2 * b[0] and b[26] > b[0] and b[28] > b[0] and b[25] == pytest.approx(b[0], abs=0.01) and b[0] > 0


def test_light_parameters_come_from_the_arrangement():
    m = meditation(light={"color": [200, 200, 200], "breath_min": 0.5, "breath_max": 0.5,
                          "stone_alpha": 0.0, "stone_width": 0},
                   breath={"period": 8})
    out = Run(m).until(0.0)[-1]
    from soundmat.light import composite
    assert (composite(out.light.layers, 108) == 100).all()
    assert m.breath.period == 8


def test_rain_rises_fast_then_eases_in_two_seconds_and_falls_as_before():
    m = meditation()
    a, b = zone(5, 0).index, zone(5, 16).index
    run = Run(m, {a: (0.0, None), b: (1.0, 12.0)})            # 第二颗 1 秒放下、12 秒拿起
    rain = lambda out: next(v for v in out.sound.voices if v.id == "weather").params
    outs = run.until(4.0)
    at = lambda t: rain(outs[round(t * 60)])
    s = lambda x: 1 - (1 - x) ** 2
    assert at(0.5)["rain"] == 0.0
    # 放下第二颗：每 0.1 秒给一次，给的是这一段结束时的值，沿先快后缓的二次曲线从 0 升到 1/3
    assert at(1.0)["rainTime"] == 0.1 and at(1.0)["rain"] == pytest.approx(s(0.05) / 3)
    assert at(2.0)["rain"] == pytest.approx(s(0.55) / 3)
    assert at(3.0)["rain"] == pytest.approx(1 / 3) and at(3.9)["rain"] == pytest.approx(1 / 3)
    # 拿起：和原来一样 1.5 秒线性回落
    out = run.until(12.1)[-1]
    assert rain(out)["rain"] == 0.0 and rain(out)["rainTime"] == 1.5


def test_weather_created_with_rain_starts_at_once():
    m = meditation()
    zs = [zone(5, k).index for k in (0, 16)]
    out = Run(m, {z: (0.0, None) for z in zs}).until(0.1)[-1]
    w = next(v for v in out.sound.voices if v.id == "weather")
    assert w.params["rain"] == pytest.approx(1 / 3) and w.params["rainTime"] == 1.5
