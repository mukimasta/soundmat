from dataclasses import replace

import pytest

from soundmat.config import SoundConfig
from soundmat.sonification.intent import Event, Position, SoundIntent, Source, Voice
from soundmat.sound.backend import RecordingBackend
from soundmat.sound.engine import SoundEngine
from soundmat.sound.spatial import PRESETS

LAT = 0.03
SYN = Source("instrument", "pad")


def make(**cfg):
    be = RecordingBackend(oneshot_length=1.0)
    base = dict(output_latency=LAT, late_tolerance=0.05, voice_budget_total=48,
                voice_budget_categories={"melodic": 12})
    base.update(cfg)
    eng = SoundEngine(be, SoundConfig(**base), PRESETS["stereo"])
    eng.add_instance("A", ["ring0", "ring1"], now=0.0)
    be.clear()
    return eng, be


def v(id, **kw):
    kw.setdefault("source", SYN)
    kw.setdefault("bus", "ring0")
    return Voice(id=id, **kw)


def kinds(be):
    return [c.kind for c in be.commands]


def test_new_keep_change_remove():
    eng, be = make()
    eng.apply("A", SoundIntent((v("a", params={"amp": 0.5}),)), now=1.0)
    (start,) = be.of_kind("start_voice")
    assert start.at == pytest.approx(1.0 + LAT)
    assert start.args["params"] == {"amp": 0.5} and start.args["oneshot"] is False
    be.clear()
    # 同一个意图再来一次：什么都不发
    eng.apply("A", SoundIntent((v("a", params={"amp": 0.5}),)), now=1.02)
    assert be.commands == []
    # 只发变化了的参数
    eng.apply("A", SoundIntent((v("a", params={"amp": 0.7, "cut": 1}),)), now=1.04)
    (upd,) = be.of_kind("set_voice")
    assert upd.args["params"] == {"amp": 0.7, "cut": 1} and upd.args["gains"] is None
    be.clear()
    # 位置变化：重新分配增益
    eng.apply("A", SoundIntent((v("a", params={"amp": 0.7, "cut": 1}, position=Position(30, 1)),)), now=1.06)
    (upd,) = be.of_kind("set_voice")
    assert upd.args["gains"] == pytest.approx([0.0, 1.0], abs=1e-9)
    be.clear()
    # 消失：按参数淡出
    eng.apply("A", SoundIntent(()), now=2.0)
    (rel,) = be.of_kind("release_voice")
    assert rel.args["fade_out"] == 0.5
    assert len(eng.voices) == 1   # 淡出完成前仍在声部表
    eng.tick(2.0 + LAT + 0.5)
    assert eng.voices == {}


def test_source_change_crossfades_old_and_new():
    eng, be = make()
    eng.apply("A", SoundIntent((v("a"),)), now=1.0)
    be.clear()
    eng.apply("A", SoundIntent((v("a", source=Source("sample", "rain.wav")),)), now=1.1)
    assert kinds(be) == ["release_voice", "start_voice"]
    assert len(eng.voices) == 2


def test_globals_diff():
    eng, be = make()
    eng.apply("A", SoundIntent(globals={"lofi": 0.2, "vol": 1}), now=1.0)
    eng.apply("A", SoundIntent(globals={"lofi": 0.3, "vol": 1}), now=1.1)
    sets = be.of_kind("set_globals")
    assert [c.args["params"] for c in sets] == [{"lofi": 0.2, "vol": 1}, {"lofi": 0.3}]


def ev(id, t, **kw):
    kw.setdefault("source", SYN)
    kw.setdefault("bus", "ring2")
    return Event(id=id, time=t, **kw)


def test_events_timestamped_deduped_and_late():
    eng, be = make()
    eng.apply("A", SoundIntent(events=(ev("e1", 1.10), ev("e2", 1.05))), now=1.0)
    starts = be.of_kind("start_voice")
    assert [c.at for c in starts] == pytest.approx([1.10 + LAT, 1.05 + LAT])
    assert all(c.args["oneshot"] for c in starts)
    be.clear()
    eng.apply("A", SoundIntent(events=(ev("e1", 1.10),)), now=1.02)
    assert be.commands == [] and eng.stats.duplicates == 1
    # 略微迟到：立即发出
    eng.apply("A", SoundIntent(events=(ev("e3", 0.95),)), now=1.0)
    assert be.of_kind("start_voice")[-1].at == pytest.approx(1.0)
    # 迟到太多：丢弃并计数
    eng.apply("A", SoundIntent(events=(ev("e4", 0.5),)), now=1.0)
    assert eng.stats.late == 1
    # 单次声音由合成器服务通知结束后移出声部表
    eng.tick(5.0)
    assert eng.voices == {}


def test_budget_ends_fading_voice_first_then_lower_priority_oldest():
    eng, be = make(voice_budget_total=2)
    eng.apply("A", SoundIntent((v("a", priority=1), v("b", priority=1))), now=1.0)
    eng.apply("A", SoundIntent((v("b", priority=1),)), now=2.0)        # a 开始淡出
    be.clear()
    eng.apply("A", SoundIntent((v("b", priority=1), v("c", priority=0))), now=2.1)
    assert kinds(be) == ["free_voice", "start_voice"]                    # 提前结束正在淡出的 a
    assert eng.stats.yields == 1
    be.clear()
    # 预算已满，新声部优先级更高：最早开始的低优先级声部让位
    eng.apply("A", SoundIntent((v("b", priority=1), v("c", priority=0), v("d", priority=5))), now=3.0)
    freed = be.of_kind("free_voice")[0].args["node"]
    assert eng.voices.get(freed) is None
    assert {r.key for r in eng.voices.values()} == {"c", "d"}   # b 最早开始，让位
    # 没有比它更低优先级的：放弃发声；之后每拍重试，但只计一次
    full = SoundIntent((v("c", priority=0), v("d", priority=5), v("e", priority=-1)))
    eng.apply("A", full, now=4.0)
    assert eng.stats.rejected == 1
    for t in (4.1, 4.2):
        eng.apply("A", full, now=t)
    assert eng.stats.rejected == 1
    assert {r.key for r in eng.voices.values()} == {"c", "d"}


def test_category_budget_steals_oldest_melodic_event():
    eng, be = make(voice_budget_categories={"melodic": 2})
    evs = tuple(ev(f"m{i}", 1.0 + i * 0.01, category="melodic", priority=0) for i in range(2))
    eng.apply("A", SoundIntent(events=evs), now=1.0)
    eng.apply("A", SoundIntent(events=(ev("m2", 1.2, category="melodic", priority=1),)), now=1.2)
    assert eng.category_count("melodic") == 2
    assert eng.stats.yields == 1
    # 还没到时刻的单次声音不让位
    eng2, _ = make(voice_budget_categories={"melodic": 1})
    eng2.apply("A", SoundIntent(events=(ev("x", 5.0, category="melodic"),)), now=1.0)
    eng2.apply("A", SoundIntent(events=(ev("y", 1.0, category="melodic", priority=3),)), now=1.0)
    assert eng2.stats.rejected == 1


def test_naturally_ended_voice_not_restarted_until_it_leaves_intent():
    eng, be = make()
    eng.apply("A", SoundIntent((v("a"),)), now=1.0)
    node = next(iter(eng.voices))
    be._ends.append((1.5, node))   # 模拟合成器服务通知它自然结束
    eng.tick(2.0)
    be.clear()
    eng.apply("A", SoundIntent((v("a"),)), now=2.1)
    assert be.commands == []
    eng.apply("A", SoundIntent(()), now=2.2)
    eng.apply("A", SoundIntent((v("a"),)), now=2.3)
    assert kinds(be) == ["start_voice"]


def test_retire_frees_everything_after_fade():
    eng, be = make()
    eng.apply("A", SoundIntent((v("a"), v("b"))), now=1.0)
    eng.add_instance("B", ["ring0"], now=1.0, fade=3.0)
    eng.retire_instance("A", now=1.0, fade=3.0)
    gains = be.of_kind("set_mix_gain")
    assert [(c.args["instance"], c.args["gain"], c.args["fade"]) for c in gains] == [("B", 1.0, 3.0), ("A", 0.0, 3.0)]
    assert eng.tick(2.0) == []
    assert eng.tick(4.1) == ["A"]
    assert eng.voices == {} and "A" not in eng.instances
    assert be.of_kind("free_mix")[0].args["instance"] == "A"


def test_restart_rebuilds_and_reconciles_once():
    eng, be = make()
    eng.set_master({"volume": 0.8}, now=0.5)
    eng.apply("A", SoundIntent((v("a"), v("b")), globals={"g": 1}), now=1.0)
    be.simulate_restart()
    be.clear()
    eng.tick(2.0)
    assert kinds(be) == ["set_master", "create_mix", "set_mix_gain", "set_globals"]
    be.clear()
    eng.apply("A", SoundIntent((v("a"), v("b")), globals={"g": 1}), now=2.0)
    assert kinds(be) == ["start_voice", "start_voice"]
    assert eng.stats.restarts == 1


def test_layout_change():
    eng, be = make()
    eng.apply("A", SoundIntent((v("a", position=Position(0, 1)),)), now=1.0)
    be.clear()
    eng.set_layout(PRESETS["stereo"], orientation=30.0, now=2.0)
    (upd,) = be.of_kind("set_voice")
    assert upd.args["gains"] == pytest.approx([0, 1], abs=1e-9)
    be.clear()
    eng.set_layout(PRESETS["quad"], orientation=0.0, now=3.0)
    assert be.of_kind("create_mix")[0].args["channels"] == 4
    assert eng.voices == {}


def test_voice_with_start_time_begins_exactly_then():
    eng, be = make()
    eng.apply("A", SoundIntent((v("bar5", start=1.08),)), now=1.0)
    (s,) = be.of_kind("start_voice")
    assert s.at == pytest.approx(1.08 + LAT)
    be.clear()
    eng.apply("A", SoundIntent((v("bar6", start=0.5),)), now=1.0)   # 已经过去：立即
    assert be.of_kind("start_voice")[0].at == pytest.approx(1.0 + LAT)
