"""scripts/render.py：离线渲染（乐谱格式、声部长度、模拟、渲染与响度）。"""
import importlib.util
import math
import struct
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile
from pythonosc.osc_message import OscMessage
from pythonosc.osc_message_builder import OscMessageBuilder

from soundmat.config import SoundConfig, load_config
from soundmat.intent import Event, SoundIntent, Source, Voice
from soundmat.perception.zones import ring_indices, zone
from soundmat.sound.engine import SoundEngine
from soundmat.sound.scsynth import MAX_DGRAM
from soundmat.sound.spatial import PRESETS

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("render_script", ROOT / "scripts" / "render.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod          # 数据类要在 sys.modules 里找到所在的模块
    spec.loader.exec_module(mod)
    return mod


render = _load()
COMPILED = load_config().synth.synthdefs_path
HAVE_DEFS = any(COMPILED.glob("*.scsyndef"))
HAVE_SCSYNTH = render.find_scsynth() is not None


def msg(address, *args):
    b = OscMessageBuilder(address)
    for a in args:
        b.add_arg(a)
    return b.build()


def read_score(path):
    """解析非实时乐谱：[(时刻, [(地址, 参数), ...], bundle 的字节数), ...]。"""
    data = Path(path).read_bytes()
    out, pos = [], 0
    while pos < len(data):
        (n,) = struct.unpack_from(">i", data, pos)
        body = data[pos + 4:pos + 4 + n]
        pos += 4 + n
        assert body[:8] == b"#bundle\x00"
        secs, frac = struct.unpack_from(">II", body, 8)
        msgs, p = [], 16
        while p < len(body):
            (size,) = struct.unpack_from(">i", body, p)
            m = OscMessage(body[p + 4:p + 4 + size])
            msgs.append((m.address, list(m.params)))
            p += 4 + size
        out.append((secs + frac / 2**32, msgs, n))
    return out


# ── 乐谱格式 ────────────────────────────────────────────────────────────────


def test_score_is_sorted_bundles_with_relative_timetags_and_an_end_marker(tmp_path):
    score = [(0.5, msg("/n_set", 1, "a", 1.0)), (0.0, msg("/g_new", 1, 0, 0)),
             (0.5, msg("/n_free", 1)), (2.0, msg("/n_free", 2))]
    path = tmp_path / "s.osc"
    assert render.write_score(score, path, 1.5) == 3            # 超过时长的指令丢掉
    bundles = read_score(path)
    assert [t for t, _, _ in bundles] == [0.0, 0.5, 1.5]
    assert [[a for a, _ in msgs] for _, msgs, _ in bundles] == [["/g_new"], ["/n_set", "/n_free"], ["/c_set"]]
    raw = path.read_bytes()
    second = raw.index(b"#bundle", 8)
    assert raw[second + 8:second + 16] == struct.pack(">II", 0, 2**31)    # 0.5 秒，不加 NTP 纪元的偏移


def test_large_bundles_are_split_keeping_order(tmp_path):
    score = [(1.0, msg("/n_set", i, *[x for k in range(40) for x in (f"p{k}", float(k))])) for i in range(30)]
    path = tmp_path / "s.osc"
    render.write_score(score, path, 2.0)
    bundles = read_score(path)[:-1]
    assert len(bundles) > 1 and all(t == 1.0 for t, _, _ in bundles)
    assert [args[0] for _, msgs, _ in bundles for _, args in msgs] == list(range(30))
    assert max(n for _, _, n in bundles) <= MAX_DGRAM + 20


# ── 声部长度 ────────────────────────────────────────────────────────────────


def scgf(name, constants, params, ugens):
    """编码一个最小的 SCgf 第 2 版文件。ugens：[(类名, [(UGen 序号或 -1, 序号), ...], 输出数, special)]。"""
    def text(s):
        return bytes([len(s)]) + s.encode()

    out = b"SCgf" + struct.pack(">ih", 2, 1) + text(name)
    out += struct.pack(f">i{len(constants)}f", len(constants), *constants)
    out += struct.pack(f">i{len(params)}f", len(params), *params.values())
    out += struct.pack(">i", len(params)) + b"".join(text(k) + struct.pack(">i", i) for i, k in enumerate(params))
    out += struct.pack(">i", len(ugens))
    for cls, inputs, n_out, special in ugens:
        out += text(cls) + struct.pack(">biih", 1, len(inputs), n_out, special)
        out += b"".join(struct.pack(">ii", u, i) for u, i in inputs) + bytes([1]) * n_out
    return out + struct.pack(">h", 0)


C = -1    # 输入是常数


def blip(name="blip_2"):
    """Line.kr(0, 0, decay + 0.5, doneAction: 2)。常数：0、2、0.5。"""
    return scgf(name, [0.0, 2.0, 0.5], {"decay": 1.0}, [
        ("Control", [], 1, 0),
        ("BinaryOpUGen", [(0, 0), (C, 2)], 1, 0),
        ("Line", [(C, 0), (C, 0), (1, 0), (C, 1)], 1, 0),
    ])


def perc():
    """EnvGen 两段（atk、decay），doneAction 2，没有释放点。常数：0、1、2、-99、5、-4。"""
    env = [(C, 0), (C, 2), (C, 3), (C, 3),                             # 起始电平、2 段、无释放点、无循环点
           (C, 1), (0, 0), (C, 1), (C, 0),                             # 每段：电平、时长、形状、曲率
           (C, 0), (0, 1), (C, 4), (C, 5)]
    return scgf("perc_2", [0.0, 1.0, 2.0, -99.0, 5.0, -4.0], {"atk": 0.01, "decay": 2.0}, [
        ("Control", [], 2, 0),
        ("EnvGen", [(C, 1), (C, 1), (C, 0), (C, 1), (C, 2)] + env, 1, 0),
    ])


def hold():
    """持续声部：Env.asr（释放点 1），门由参数 gate 控制，doneAction 2。常数：0、1、2、-99、0.5。"""
    env = [(C, 0), (C, 2), (C, 1), (C, 3), (C, 1), (0, 1), (C, 1), (C, 0), (C, 0), (C, 4), (C, 1), (C, 0)]
    return scgf("hold_2", [0.0, 1.0, 2.0, -99.0, 0.5], {"gate": 1.0, "atk": 0.05}, [
        ("Control", [], 2, 0),
        ("EnvGen", [(0, 0), (C, 1), (C, 0), (C, 1), (C, 2)] + env, 1, 0),
    ])


def graph(data, tmp_path, name="g"):
    path = tmp_path / f"{name}.scsyndef"
    path.write_bytes(data)
    return render.read_synthdef(path)


def test_lifetime_from_line_and_envelope_with_the_voice_params(tmp_path):
    g = graph(blip(), tmp_path)
    assert g.name == "blip_2" and g.params == {"decay": 0}
    assert render.synth_lifetime(g, {}) == pytest.approx(1.5)
    assert render.synth_lifetime(g, {"decay": 4.0, "freq": 9.0}) == pytest.approx(4.5)
    assert render.synth_lifetime(graph(perc(), tmp_path), {"atk": 0.5}) == pytest.approx(2.5)


def test_gated_envelope_never_ends_and_unknown_inputs_give_none(tmp_path):
    assert render.synth_lifetime(graph(hold(), tmp_path), {"gate": 1.0}) == math.inf
    noisy = scgf("noisy_2", [0.0, 2.0], {}, [
        ("Rand", [(C, 0), (C, 1)], 1, 0),
        ("Line", [(C, 0), (C, 0), (0, 0), (C, 1)], 1, 0),
    ])
    assert render.synth_lifetime(graph(noisy, tmp_path), {}) is None
    choose = scgf("choose_2", [0.0, 2.0, 0.1, 0.3], {"far": 0.0}, [
        ("Control", [], 1, 0),
        ("Select", [(0, 0), (C, 2), (C, 3)], 1, 0),
        ("Line", [(C, 0), (C, 0), (1, 0), (C, 1)], 1, 0),
    ])
    g = graph(choose, tmp_path)
    assert render.synth_lifetime(g, {}) == pytest.approx(0.1)
    assert render.synth_lifetime(g, {"far": 1.0}) == pytest.approx(0.3)
    assert render.synth_lifetime(g, {"far": 7.0}) == pytest.approx(0.3)      # 和 Select 一样截到范围内


@pytest.mark.skipif(not HAVE_DEFS, reason="音色没有编译")
def test_lifetimes_of_the_real_instruments_follow_their_sources():
    """与 instruments/ 里写的长度一致（见各音色的 doneAction）。"""
    def life(name, **params):
        return render.synth_lifetime(render.read_synthdef(COMPILED / f"{name}.scsyndef"), params)

    assert life("pool_distant_2", decay=8.0) == pytest.approx(0.2 + 8 + 3)
    assert life("pool_note_echo_8", noteAtk=0.08, decay=5.5) == pytest.approx(0.08 + 0.1 + 5.5 + 5)
    assert life("pool_thunder_2", tAtk=0.55, sus=2.05, tRel=8.0) == pytest.approx(10.6)
    assert life("jam_rhodes_2", far=1.0, sustain=2.0) == pytest.approx(2.0 + 0.9)
    assert life("jam_rhodes_2", sustain=0.1) == pytest.approx(0.003 + 0.58 + 0.01 + 0.85)
    assert life("jam_pluck_bass_4", sustain=0.5) == pytest.approx(0.9)       # 两个包络，先结束的那个
    assert life("pool_bed_2", gate=1.0) == math.inf
    assert life("sm_play_stereo_2") is None                                  # 放完素材为止：按素材长度算


def test_sample_length_from_the_file_and_unknown_instruments_use_the_default(tmp_path):
    from types import SimpleNamespace

    info = SimpleNamespace(frames=96000, sample_rate=48000, channels=1)
    lt = render.Lifetimes(tmp_path, lambda ref: info if ref == "a.wav" else None)
    sample = Source("sample", "a.wav")
    assert lt.of(sample, {}, 2, oneshot=True) == pytest.approx(2.0)
    assert lt.of(sample, {"rate": 2.0, "startPos": 48000}, 2, oneshot=True) == pytest.approx(0.5)
    assert lt.of(sample, {}, 2, oneshot=False) == math.inf                   # 循环播放
    assert lt.of(Source("instrument", "nope"), {}, 2, oneshot=True) == render.DEFAULT_ONESHOT
    assert lt.of(Source("instrument", "nope"), {}, 2, oneshot=False) == math.inf
    assert lt.guessed == {"nope"}


# ── 乐谱后端 ────────────────────────────────────────────────────────────────


@pytest.fixture
def score_rig(tmp_path):
    defs = tmp_path / "defs"
    defs.mkdir()
    (defs / "blip_2.scsyndef").write_bytes(blip())
    (defs / "hold_2.scsyndef").write_bytes(hold())
    be = render.ScoreBackend(defs)
    eng = SoundEngine(be, SoundConfig(schedule_ahead=0.15), PRESETS["stereo"])
    eng.add_instance("A", ["ring0"], 0.0)
    return be, eng


def step(be, eng, t, intent=None):
    be.now = t
    if intent is not None:
        eng.apply("A", intent, t)
    eng.tick(t)
    be.flush()


def test_score_backend_ends_oneshots_and_released_voices_on_time(score_rig):
    be, eng = score_rig
    pad = Voice("pad", Source("instrument", "hold"), "ring0", fade_out=1.0)
    step(be, eng, 0.0, SoundIntent((pad,), (Event("now", None, Source("instrument", "blip"), "ring0", {"decay": 0.5}),
                                            Event("later", 0.5, Source("instrument", "blip"), "ring0"))))
    assert len(eng.voices) == 3
    step(be, eng, 0.99)
    assert len(eng.voices) == 3                  # 立即的那个 0 秒开始，1.0 秒结束
    step(be, eng, 1.0)
    assert len(eng.voices) == 2
    step(be, eng, 2.1, SoundIntent())            # 定时的那个 0.65 秒开始、2.15 秒结束；持续声部开始淡出
    assert len(eng.voices) == 2
    step(be, eng, 2.16)
    assert len(eng.voices) == 1
    step(be, eng, 3.09)
    assert len(eng.voices) == 1
    step(be, eng, 3.11)                          # 淡出 1 秒
    assert eng.voices == {}
    news = [(round(t, 6), m.params[0]) for t, m in be.score if m.address == "/s_new"]
    assert (0.0, "hold_2") in news and (0.0, "blip_2") in news and (0.65, "blip_2") in news


def test_score_backend_keeps_the_live_order_within_a_beat(score_rig):
    """同一拍里立即执行的单条指令先于一拍结束时成批发出的定时指令（与实时连接相同）。"""
    be, eng = score_rig
    be.flush()
    be.now = 1.0
    be.schedule(1.0, msg("/n_set", 1, "a", 1.0))
    be.send(msg("/b_allocRead", 0, "x.wav"))
    be.flush()
    assert [m.address for t, m in be.score if t == 1.0] == ["/b_allocRead", "/n_set"]
    assert [m.address for t, m in be.score[:2]] == ["/d_loadDir", "/g_freeAll"]


# ── 时间表与模拟 ────────────────────────────────────────────────────────────


def test_scenario_validation():
    ok = render.Scenario.from_json({"duration": 10, "stones": [{"ring": 7, "slot": 31, "on": 0, "off": None}]})
    assert ok.stones[0].zone == zone(7, 31).index
    for bad in ({"duration": 0},
                {"duration": 5, "stones": [{"ring": 8, "slot": 0, "on": 0}]},
                {"duration": 5, "stones": [{"ring": 1, "slot": 16, "on": 0}]},
                {"duration": 5, "stones": [{"ring": 1, "slot": 0, "on": 2, "off": 1}]},
                {"duration": 5, "control": [{"on": 0, "off": None, "pressure": 0.1}]}):
        with pytest.raises(ValueError):
            render.Scenario.from_json(bad)


def test_reference_scenes_are_valid():
    scenes = sorted((ROOT / "scripts" / "scenes").glob("*.json"))
    assert scenes
    for path in scenes:
        assert render.Scenario.load(path).duration > 0


def test_pressure_map_from_stones_and_control_pressure():
    cfg = load_config().mat
    sc = render.Scenario.from_json({"duration": 10,
                                    "stones": [{"ring": 0, "slot": 0, "on": 1, "off": 2}, {"ring": 5, "slot": 3, "on": 1}],
                                    "control": [{"on": 0, "off": 5, "pressure": 1000}, {"on": 4, "pressure": 3000}]})
    control = frozenset(list(ring_indices(0)) + list(ring_indices(1)))
    early = sc.pressure(0.5, 0, control, cfg).values
    assert early.sum() * cfg.full_scale == pytest.approx(1000, abs=0.1)
    assert early[list(control)].min() == early[list(control)].max()          # 平均分到各控制区
    both = sc.pressure(1.5, 1, control, cfg).values
    assert both[zone(5, 3).index] == pytest.approx(0.5)
    assert both[list(control)].sum() == pytest.approx(1000 / cfg.full_scale + 0.5)   # 控制区上的石头也算
    later = sc.pressure(4.5, 2, control, cfg).values                         # 两段相加；控制区上的石头已经拿起
    assert later[list(control)].sum() * cfg.full_scale == pytest.approx(4000, abs=0.5)
    assert sc.pressure(4.5, 2, frozenset(), cfg).values.sum() == pytest.approx(0.5)  # 没有控制区就没有额外压力


def test_simulate_meditation_without_compiled_instruments(tmp_path):
    """不需要 SuperCollider：音色目录是空的，单次声音按默认长度估算。"""
    defs = tmp_path / "defs"
    defs.mkdir()
    sc = render.Scenario.from_json({"duration": 3, "stones": [{"ring": 0, "slot": 3, "on": 0.5}]})
    sim = render.simulate(render.find_arrangement("meditation"), sc, synthdefs=defs, sound_dir=tmp_path)
    news = [(t, m.params[0]) for t, m in sim.score if m.address == "/s_new"]
    assert news[0] == (0.0, "sm_master_2") and (0.0, "pool_bed_2") in news
    drone = next(t for t, name in news if name.startswith("pool_drone"))
    assert 0.54 <= drone <= 0.6                                              # 放下 0.5 秒，去抖 0.04 秒
    assert sim.counters["restarts"] == 0 and sim.peak_voices >= 2 and not sim.missing
    assert [m.address for _, m in sim.score[:3]] == ["/d_loadDir", "/g_freeAll", "/g_new"]


def test_simulate_jam_starts_with_control_pressure(tmp_path):
    defs = tmp_path / "defs"
    defs.mkdir()
    stones = [{"ring": r, "slot": 4 * k, "on": 0.2} for r in (2, 4, 6) for k in range(3)]

    def notes(pressure):
        data = {"duration": 6, "stones": stones}
        if pressure:
            data["control"] = [{"on": 0.5, "off": None, "pressure": pressure}]
        sim = render.simulate(render.find_arrangement("lofi_1"), render.Scenario.from_json(data),
                              synthdefs=defs, sound_dir=tmp_path)
        return sum(1 for t, m in sim.score if m.address == "/s_new" and str(m.params[0]).startswith("jam_"))

    assert notes(3000) > notes(0) + 10                                       # 按住控制区才开始演奏


def test_budget_is_lifted_unless_asked(tmp_path):
    defs = tmp_path / "defs"
    defs.mkdir()
    sc = render.Scenario.from_json({"duration": 1})
    loose = render.simulate(render.find_arrangement("meditation"), sc, synthdefs=defs, sound_dir=tmp_path)
    real = render.simulate(render.find_arrangement("meditation"), sc, synthdefs=defs, sound_dir=tmp_path,
                           real_budget=True)
    assert not loose.real_budget and real.real_budget
    assert loose.budget == real.budget == (load_config().sound.voice_budget_total,
                                           dict(load_config().sound.voice_budget_categories))


# ── 响度 ────────────────────────────────────────────────────────────────────


def test_k_weighting_matches_bs1770_at_48k():
    (shelf_b, shelf_a), (hp_b, hp_a) = render._k_weighting(48000)
    assert shelf_b == pytest.approx([1.53512485958697, -2.69169618940638, 1.19839281085285], abs=1e-9)
    assert shelf_a == pytest.approx([1.0, -1.69065929318241, 0.73248077421585], abs=1e-9)
    assert hp_a == pytest.approx([1.0, -1.99004745483398, 0.99007225036621], abs=1e-9)


def test_loudness_of_a_sine_and_silence_is_gated(tmp_path):
    """BS.1770：一个声道上 0 dBFS 的 1 kHz 正弦是 -3.01 LUFS；两个声道各 -20 dBFS 就是 -20 LUFS。
    后面接 5 秒静音：静音的块被绝对门限去掉，只剩跨在边界上的 3 个块（3/4、1/2、1/4 有声）留下。"""
    sr = 48000
    t = np.arange(5 * sr) / sr
    sine = 0.1 * np.sin(2 * np.pi * 1000 * t)
    x = np.stack([sine, sine], axis=1)
    assert render.integrated_loudness(x, sr) == pytest.approx(-20.0, abs=0.02)
    padded = np.concatenate([x, np.zeros((5 * sr, 2))])
    assert render.integrated_loudness(padded, sr) == pytest.approx(-20 + 10 * math.log10(48.5 / 50), abs=0.02)
    path = tmp_path / "s.wav"
    soundfile.write(path, np.concatenate([padded, np.zeros((sr // 2, 2))]), sr, subtype="FLOAT")
    st = render.audio_stats(path)
    assert st.peak == pytest.approx(-20.0, abs=0.01)
    assert len(st.windows) == 1 and st.windows[0] == pytest.approx(-26.0, abs=0.05)   # 半段正弦：-23 再减 3 dB


# ── 真实渲染 ────────────────────────────────────────────────────────────────


@pytest.mark.skipif(not (HAVE_SCSYNTH and HAVE_DEFS), reason="需要本机的 scsynth 和编译好的音色")
def test_render_a_short_scene(tmp_path, capsys):
    """scsynth 非实时渲染一段很短的场景：文件写出来、长度和声道对、有声音、没有报错。"""
    scenario = tmp_path / "s.json"
    scenario.write_text('{"duration": 3, "stones": [{"ring": 0, "slot": 3, "on": 0.5, "off": null}]}')
    out = tmp_path / "out.wav"
    assert render.main(["meditation", str(scenario), str(out), "--stats", "--channels", "4"]) == 0
    text = capsys.readouterr().out
    assert "scsynth 报错：无" in text and "LUFS" in text
    info = soundfile.info(out)
    assert info.channels == 4 and info.samplerate == 48000
    assert info.frames == pytest.approx(3 * 48000, abs=128)
    x, _ = soundfile.read(out)
    assert 1e-4 < np.abs(x).max() < 1.0
