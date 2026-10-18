import numpy as np
import pytest

from soundmat.clock import Beat
from soundmat.perception.model import MatEvent, MatSnapshot, MatState, PressureMap
from soundmat.perception.zones import NUM_ZONES, ZONES, zone
from soundmat.sonification.ambient import AmbientMode
from soundmat.sonification.arrangements import ARRANGEMENTS_DIR, load_arrangement
from soundmat.sonification.mode import Arrangement, LoadError, ModeContext

CTX = ModeContext(led_count=108, seed=7)


def snap(t, zones):
    counts = [0] * 8
    for z in zones:
        counts[ZONES[z].ring] += 1
    return MatSnapshot(
        pressure=PressureMap(t, 0, np.zeros(NUM_ZONES, dtype=np.float32)),
        state=MatState(t, frozenset(zones), tuple(counts), None),
    )


def place(t, z):
    return MatEvent("place", z, t)


def kyoto():
    m = AmbientMode(load_arrangement(ARRANGEMENTS_DIR / "kyoto"), CTX)
    m.plan = m.load()
    m.start(0.0)
    return m


def test_kyoto_plan():
    m = kyoto()
    assert len(m.plan.assets) == 14
    assert all(a.startswith("kyoto/") for a in m.plan.assets)
    assert m.plan.instruments == {"diapasonHold", "marimbaNote"}


def test_sustained_and_tiers_change_identity():
    m = kyoto()
    a, b = zone(3, 0).index, zone(3, 8).index
    out = m.tick(Beat(0, 1.0, 1 / 60), snap(1.0, [a]), [])
    ids = {v.id for v in out.sound.voices}
    wind1 = next(v for v in out.sound.voices if v.id.startswith("r3.wind"))
    assert wind1.source.name.endswith("335891__yoyodaman234__bamboo-creaking-in-wind.wav")
    assert wind1.params["amp"] == -15 and wind1.bus == "ring3"
    assert wind1.fade_in == 0.5 and wind1.fade_out == 1.5      # 来自 defaults 的 atk / rel
    assert "r3.stream" in ids
    out = m.tick(Beat(1, 1.1, 1 / 60), snap(1.1, [a, b]), [])
    wind2 = next(v for v in out.sound.voices if v.id.startswith("r3.wind"))
    assert wind2.id != wind1.id and wind2.params["amp"] == -11
    assert out.status.text == "每环一层 · 左右两只音箱"


def test_instrument_sustained_uses_role_fades():
    m = kyoto()
    out = m.tick(Beat(0, 1.0, 1 / 60), snap(1.0, [zone(0, 3).index]), [])
    drone = next(v for v in out.sound.voices if v.id == "r0.drone")
    assert drone.source.kind == "instrument" and drone.source.name == "diapasonHold"
    assert (drone.fade_in, drone.fade_out) == (4.0, 6.0)
    assert drone.params == {"freq": 130.81, "amp": -10.0}
    assert drone.position is None


def test_triggers_pitch_and_position_follow_zone():
    m = kyoto()
    z = zone(5, 2)
    out = m.tick(Beat(0, 1.0, 1 / 60), snap(1.0, [z.index]), [place(1.0, z.index)])
    (hit,) = [e for e in out.sound.events if ".hit#" in e.id]
    assert hit.params["freq"] == pytest.approx(440 * 2 ** ((64 - 69) / 12))   # 第 2 级：E4
    assert hit.position.angle == pytest.approx(z.center_deg)
    assert hit.time is None                       # 对放下石头的反应：立即发声
    # 对称：第 30 区与第 2 区同音
    z2 = zone(5, 30)
    out = m.tick(Beat(1, 1.1, 1 / 60), snap(1.1, [z.index, z2.index]), [place(1.1, z2.index)])
    (hit2,) = [e for e in out.sound.events if ".hit#" in e.id]
    assert hit2.params["freq"] == pytest.approx(hit.params["freq"])
    assert hit2.id != hit.id


def test_intermittent_waits_random_interval_and_stops_when_empty():
    m = kyoto()
    z = zone(5, 0).index
    times = []
    t = 0.0
    while t < 60:
        out = m.tick(Beat(0, t, 0.1), snap(t, [z]), [])
        times += [t for e in out.sound.events if ".marimba#" in e.id]    # 立即发声：就在这一拍
        t += 0.1
    gaps = np.diff([0.0] + times)
    assert len(times) >= 3
    assert all(4.9 <= g <= 15.2 for g in gaps)
    out = m.tick(Beat(0, 61, 0.1), snap(61, []), [])
    assert m.next_fire == {}


def test_conditions_and_centroid():
    arr = Arrangement("c", "C", "ambient", content={
        "samples": {"rain": {"file": "rain.wav"}, "leaves": {"file": "leaves.wav"}},
        "rings": {"4": {
            "rain": {"behavior": "sustained", "samples": ["rain"], "unless_rings": [3], "position": "centroid"},
            "leaves": {"behavior": "sustained", "samples": ["leaves"], "when_rings": [3]},
        }},
    })
    m = AmbientMode(arr, CTX)
    m.load()
    m.start(0)
    a, b = zone(4, 0).index, zone(4, 8).index   # 0° 和 90°
    out = m.tick(Beat(0, 1, 0.1), snap(1, [a, b]), [])
    (rain,) = out.sound.voices
    assert rain.id == "r4.rain" and rain.position.angle == pytest.approx(45.0)
    out = m.tick(Beat(1, 2, 0.1), snap(2, [a, b, zone(3, 1).index]), [])
    assert [v.id for v in out.sound.voices] == ["r4.leaves"]


@pytest.mark.parametrize("content, msg", [
    ({"rings": {}}, "没有任何角色"),
    ({"rings": {"1": {"x": {"behavior": "loud", "instrument": "a"}}}}, "behavior"),
    ({"rings": {"1": {"x": {"behavior": "trigger"}}}}, "instrument"),
    ({"rings": {"1": {"x": {"behavior": "trigger", "samples": ["nope"]}}}}, "不存在的素材"),
    ({"rings": {"1": {"x": {"behavior": "intermittent", "instrument": "a"}}}}, "interval"),
    ({"rings": {"1": {"x": {"behavior": "trigger", "instrument": "a", "amp": "loud"}}}}, "不是数值"),
])
def test_load_errors(content, msg):
    with pytest.raises(LoadError, match=msg):
        AmbientMode(Arrangement("x", "X", "ambient", content=content), CTX).load()


def test_lights_breath_and_stone_marks():
    m = kyoto()
    z = zone(2, 0).index   # 0° → 灯珠 0
    out = m.tick(Beat(0, 1, 0.1), snap(1, [z]), [])
    base, marks = out.light.layers
    assert base.alpha.min() > 0
    assert marks.alpha[0] > 0 and marks.alpha[54] == 0


class _ReferenceCanvas:
    """第一版逐灯珠的画法（0–1 颜色），作对照。"""

    def __init__(self, n):
        self.n = n
        self.rgb = np.zeros((n, 3), dtype=np.float32)
        self.alpha = np.zeros(n, dtype=np.float32)

    def fill(self, color, alpha):
        self.rgb[:] = np.asarray(color, dtype=np.float32) / 255.0
        self.alpha[:] = alpha
        return self

    def put(self, index, color, alpha):
        i = index % self.n
        a0 = self.alpha[i]
        a = max(a0, alpha)
        if a <= 0:
            return
        c = np.asarray(color, dtype=np.float32) / 255.0
        w = alpha / (a0 + alpha) if (a0 + alpha) > 0 else 1.0
        self.rgb[i] = self.rgb[i] * (1 - w) + c * w
        self.alpha[i] = a

    def span(self, center, width, color, alpha):
        half = max(0, width // 2)
        for d in range(-half, half + 1):
            self.put(center + d, color, alpha * (1.0 - abs(d) / (half + 1)))


@pytest.mark.parametrize("seed", range(20))
def test_lights_match_per_led_reference(seed):
    """Ambient 灯光改用共用的向量化画布后，与原来逐灯珠的画法一致（相邻石头的标记叠加也一样）。"""
    import math
    import random

    from soundmat.sonification.ambient import WARM
    from soundmat.sonification.lights import RING_COLORS, led_for_angle

    rnd = random.Random(seed)
    n = 108
    t = rnd.uniform(0, 100)
    s = snap(t, {rnd.randrange(NUM_ZONES) for _ in range(rnd.randint(0, 80))})
    mode = AmbientMode(Arrangement("a", "A", "ambient", content={}), ModeContext(led_count=n))
    base, marks = mode._light(t, s).layers

    breath = 0.25 + 0.2 * (0.5 + 0.5 * math.sin(t * 0.9))
    ref_base = _ReferenceCanvas(n).fill(WARM, breath)
    ref_marks = _ReferenceCanvas(n)
    for z in s.state.occupied:
        ref_marks.span(led_for_angle(ZONES[z].center_deg, n), 3, RING_COLORS[ZONES[z].ring], 0.55)
    np.testing.assert_allclose(base.rgb, ref_base.rgb, atol=1e-5)
    np.testing.assert_allclose(base.alpha, ref_base.alpha, atol=1e-6)
    np.testing.assert_allclose(marks.rgb, ref_marks.rgb, atol=1e-5)
    np.testing.assert_allclose(marks.alpha, ref_marks.alpha, atol=1e-6)
