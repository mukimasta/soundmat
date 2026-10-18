import os
import socket
import time
from types import SimpleNamespace

import pytest

from soundmat.timebase import system_time
from soundmat.config import SoundConfig
from soundmat.intent import Event, Position, SoundIntent, Source, Voice
from soundmat.sound.engine import SoundEngine
from soundmat.sound.scsynth import Allocator, ScsynthBackend
from soundmat.sound.spatial import PRESETS

from fake_scsynth import FakeScsynth, reply


@pytest.fixture
def rig(tmp_path):
    fake = FakeScsynth()
    defs = tmp_path / "defs"
    defs.mkdir()
    wav = SimpleNamespace(path=tmp_path / "a.wav", channels=2)
    be = ScsynthBackend(port=fake.port, synthdefs=defs, resolve_asset=lambda ref: wav if ref == "a.wav" else None)
    eng = SoundEngine(be, SoundConfig(schedule_ahead=0.15), PRESETS["stereo"])
    yield fake, be, eng
    fake.close()


def pump(eng, be, seconds=0.3, until=None):
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        now = system_time()
        eng.tick(now)
        be.flush()
        if until and until():
            return True
        time.sleep(0.01)
    return until() if until else True


def test_allocator_first_fit_and_merge():
    a = Allocator(0, 10)
    x, y = a.alloc(4), a.alloc(4)
    assert (x, y) == (0, 4)
    a.release(0, 4)
    a.release(4, 4)
    assert a.free == [(0, 10)]
    with pytest.raises(RuntimeError):
        a.alloc(11)


def test_connect_loads_defs_builds_tree_and_reports_restart(rig):
    fake, be, eng = rig
    eng.add_instance("A", ["ring0", "harmony"], system_time())     # 离线时：什么都不发
    assert pump(eng, be, 2, until=lambda: be.state == "ready" and be.mixes)
    assert eng.stats.restarts == 1
    time.sleep(0.15)
    assert fake.of("/notify") and fake.of("/d_loadDir")
    addrs = [m[1] for m in fake.messages]
    assert addrs.index("/g_freeAll") < addrs.index("/g_new")
    news = [m[2][0] for m in fake.of("/s_new")]
    assert {"sm_master_2", "sm_fx_freeverb_2", "sm_mode_2"} <= set(news)
    assert be.info["nominalSampleRate"] == 48000.0


def test_voice_messages_timestamps_and_globals(rig):
    fake, be, eng = rig
    eng.add_instance("A", ["ring0", "ring5"], system_time(), fx="sm_fx_jam")
    pump(eng, be, 2, until=lambda: be.state == "ready" and be.mixes)
    time.sleep(0.15)
    assert any(m[2][0] == "sm_fx_jam_2" for m in fake.of("/s_new"))
    fake.messages.clear()
    now = system_time()
    eng.apply("A", SoundIntent(
        (Voice("d", Source("instrument", "diapasonHold"), "ring0", {"freq": 130.0}, fade_in=4.0),),
        (Event("e", now + 0.5, Source("instrument", "marimbaNote"), "ring5", {"freq": 440.0}, Position(30, 1)),),
        {"cutoff": 2000.0, "bus.ring5": 0.5, "fx.decay": 2.0},
    ), now)
    be.flush()
    time.sleep(0.2)
    s_new = {m[2][0]: m for m in fake.of("/s_new")}
    drone = s_new["diapasonHold_2"]
    args = drone[2]
    kv = dict(zip(args[4::2], args[5::2]))
    assert kv["atk"] == pytest.approx(4.0) and kv["gate"] == 1 and kv["freq"] == pytest.approx(130.0)
    assert {"g0", "g1", "gl0", "gr1", "out", "fx"} <= kv.keys()
    hit = s_new["marimbaNote_2"]
    assert hit[0] == pytest.approx(time.time() + 0.33, abs=0.15)      # 0.5 + 输出延迟，换算为墙钟
    kv = dict(zip(hit[2][4::2], hit[2][5::2]))
    assert "gate" not in kv and kv["g1"] == pytest.approx(1.0, abs=1e-6)
    sets = fake.of("/n_set")
    flat = [a for m in sets for a in m[2]]
    assert "cutoff" in flat and "gain1" in flat and "decay" in flat


def test_n_end_and_missing_sample_end_voices(rig, tmp_path):
    fake, be, eng = rig
    eng.add_instance("A", ["ring0"], system_time())
    pump(eng, be, 2, until=lambda: be.state == "ready" and be.mixes)
    be.load_asset("a.wav", system_time())
    time.sleep(0.15)
    assert fake.of("/b_allocRead")[0][2][1].endswith("a.wav")
    now = system_time()
    eng.apply("A", SoundIntent((
        Voice("s", Source("sample", "a.wav"), "ring0"),
        Voice("gone", Source("sample", "missing.wav"), "ring0"),
    )), now)
    be.flush()
    time.sleep(0.1)
    assert any(m[2][0] == "sm_play_stereo_2" for m in fake.of("/s_new"))
    node = next(n for n, r in eng.voices.items() if r.key == "s")
    fake.send(reply("/n_end", node, 0, -1, -1, 0))
    pump(eng, be, 0.3)
    assert eng.voices == {}                      # 缺失的素材当作立即结束；n_end 移出声部表
    assert eng.instances["A"].finished == {"s", "gone"}


def test_restart_detected_by_lost_root_group_and_offline(rig):
    fake, be, eng = rig
    eng.add_instance("A", ["ring0"], system_time())
    pump(eng, be, 2, until=lambda: be.state == "ready" and be.mixes)
    fake.nodes_lost = True
    assert pump(eng, be, 2, until=lambda: eng.stats.restarts == 2)
    fake.alive = False
    assert pump(eng, be, 3.5, until=lambda: be.state == "offline")
    assert not be.online
    fake.alive = True
    assert pump(eng, be, 2, until=lambda: eng.stats.restarts == 3)
    assert be.mixes


def test_host_stall_is_not_mistaken_for_synth_offline(rig):
    """主机的节拍线程卡住几秒（期间没有发查询）：恢复后不应判定合成器服务离线、重建混音结构、停掉录音。"""
    fake, be, eng = rig
    eng.add_instance("A", ["ring0"], system_time())
    assert pump(eng, be, 2, until=lambda: be.state == "ready" and be.mixes)
    restarts = eng.stats.restarts
    time.sleep(0.2)                     # 最后一次查询的回复到了
    eng.tick(system_time())
    time.sleep(3.0)                     # 卡住 3 秒：超过 2 秒的离线判定，但期间没有发出任何查询
    pump(eng, be, 0.5)
    assert be.state == "ready" and be.online and eng.stats.restarts == restarts


def test_levels_per_meter(rig):
    """每根电平条取它的各条总线、所有声道的最大峰值；不认识的实例或总线是静音。"""
    fake, be, eng = rig
    eng.add_instance("A", [f"ring{r}" for r in range(8)] + ["harmony", "drums"], system_time())
    pump(eng, be, 2, until=lambda: be.state == "ready" and be.mixes)
    mix = be.mixes["A"]
    fake.send(reply("/sm_peak", be.master_node, 100, 0.5, 0.1, 0.25, 0.05))
    fake.send(reply("/sm_peak", mix.mode_node, 3, 0.1, 0.0, 1.0, 0.0))        # ring3：左 0.1、右 1.0
    fake.send(reply("/sm_peak", mix.mode_node, 8, 0.05, 0.0, 0.02, 0.0))      # harmony
    fake.send(reply("/sm_peak", mix.mode_node, 9, 0.5, 0.0, 0.1, 0.0))        # drums
    pump(eng, be, 0.2)
    lv = be.levels("A", [["ring3"], ["harmony", "drums"], ["ring0"], ["nope"]])
    assert lv["output"] == pytest.approx([-6.0, -12.0], abs=0.1)
    assert lv["meters"] == pytest.approx([0.0, -6.0, -120.0, -120.0], abs=0.1)
    assert be.levels("other", [["ring3"]])["meters"] == [-120.0]


def _live_enabled():
    """连真实 scsynth 的测试会清空它的节点树、发声并录音，所以必须显式打开（CI 里打开）；
    否则开发时会打断本机正在试听的合成器服务。"""
    return os.environ.get("SOUNDMAT_LIVE_SCSYNTH") == "1" and _scsynth_running()


def _scsynth_running():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0.3)
    try:
        s.sendto(b"/status\x00,\x00\x00\x00", ("127.0.0.1", 57110))
        s.recvfrom(1024)
        return True
    except OSError:
        return False
    finally:
        s.close()


@pytest.mark.skipif(not _live_enabled(), reason="需要 SOUNDMAT_LIVE_SCSYNTH=1 和本机运行的 scsynth")
def test_live_scsynth_plays_jam(make_sup, tmp_path, monkeypatch):
    """真实的 scsynth（云端用 JACK dummy 驱动）：编排在合成器服务里建立并产生电平。"""
    from soundmat.config import load_config
    from soundmat.perception.zones import ring_indices, zone

    if not load_config().synth.synthdefs_path.is_dir():
        pytest.skip("音色没有编译")
    monkeypatch.setenv("SOUNDMAT_SOUND", str(tmp_path / "no-sound"))
    sup = make_sup(synth="scsynth")
    sup.start()
    for z in list(ring_indices(0))[:2] + [zone(7, 0).index]:
        sup.virtual.set(z, True)
    sup.catalog.play("lofi_1")
    deadline = time.monotonic() + 8
    lv = None
    while time.monotonic() < deadline:
        lv = sup.sonification.levels.get()
        if lv and max(lv["output"] or [-120]) > -60:
            break
        time.sleep(0.2)
    assert sup.backend.status()["state"] == "ready"
    assert lv and max(lv["output"]) > -60


@pytest.mark.skipif(not _live_enabled(), reason="需要 SOUNDMAT_LIVE_SCSYNTH=1 和本机运行的 scsynth")
def test_live_recording_starts_at_the_slate(make_sup, tmp_path, monkeypatch):
    """真实的 scsynth 录下总输出和分轨；录音从打板（按下后 3 秒）开始，提示音只在现场响、不进录音。"""
    import numpy as np
    import soundfile

    from soundmat.config import load_config

    if not load_config().synth.synthdefs_path.is_dir():
        pytest.skip("音色没有编译")
    monkeypatch.setenv("SOUNDMAT_SOUND", str(tmp_path / "no-sound"))
    sup = make_sup(synth="scsynth", monitor=False)
    sup.start()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not (sup.backend.online and sup.backend.mixes):
        time.sleep(0.1)
    time.sleep(0.5)
    sup.recorder.request_start()
    time.sleep(4.5)
    sup.recorder.request_stop()
    time.sleep(1.0)
    item = sup.store.get("catalog.recordings")[0]
    folder = sup.recorder.folder_of(item["name"])
    assert item["audio"] is True and (folder / "stems" / "fx.wav").exists()
    x, sr = soundfile.read(folder / "master.wav")
    assert len(x) / sr == pytest.approx(4.5 - 3.0 + 0.15, abs=0.3)    # 从打板录到停止（加上提前量）
    assert np.abs(x).max() < 0.01                                    # 没有石头：文件里一片安静，没有提示音


def test_node_ids_are_never_reused_across_reconnects(rig):
    """重连后新建的混音组不能和旧的同号：否则排在未来时刻、清空节点树之后才执行的旧指令，
    会把声音建进新组里，成为没人释放的节点。"""
    fake, be, eng = rig
    eng.add_instance("A", ["ring0"], system_time())
    assert pump(eng, be, 2, until=lambda: be.state == "ready" and be.mixes)
    before = {be.mixes["A"].group, be.mixes["A"].mode_node, be.master_node}
    fake.nodes_lost = True                                     # 合成器服务"重启"：引擎重连并重建
    assert pump(eng, be, 2, until=lambda: eng.stats.restarts == 2 and be.mixes)
    after = {be.mixes["A"].group, be.mixes["A"].mode_node, be.master_node}
    assert before.isdisjoint(after)
