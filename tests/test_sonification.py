import numpy as np
import pytest

from soundmat.perception.model import PressureMap
from soundmat.perception.zones import NUM_ZONES
from soundmat.sonification.mode import LoadError
from soundmat.supervisor import Options, Supervisor

from helpers import EchoMode, arrangement, beat


@pytest.fixture
def sup(config):
    return Supervisor(config, Options(virtual=True, modes={"echo": EchoMode}))


def press(sup, t, zones):
    v = np.zeros(NUM_ZONES, dtype=np.float32)
    v[list(zones)] = 0.5
    sup.perception.feed(PressureMap(t=t, seq=0, values=v))


def test_lifecycle_voices_events_status(sup):
    sup.switch(arrangement())
    son, be = sup.sonification, sup.backend
    son.on_beat(beat(0, 1.0))
    assert sup.store.get("status.current.arrangement") == "echo"
    assert son.active.mode.started == 1.0
    press(sup, 1.0, [40])
    press(sup, 1.1, [40])          # 去抖后放下
    son.on_beat(beat(1, 1.12))
    starts = be.of_kind("start_voice")
    assert sorted(c.args["oneshot"] for c in starts) == [False, True]
    assert sup.store.get("status.current.modeStatus")["text"] == "1 颗"
    # 事件只交给一次
    son.on_beat(beat(2, 1.14))
    assert len(be.of_kind("start_voice")) == 2


def test_load_failure_keeps_current(sup):
    sup.switch(arrangement("a"))
    sup.sonification.on_beat(beat(0, 1.0))
    with pytest.raises(LoadError):
        sup.switch(arrangement("b", broken=True))
    with pytest.raises(LoadError):
        sup.switch(arrangement("c").__class__(id="c", title="C", mode="nope"))
    sup.sonification.on_beat(beat(1, 1.1))
    assert sup.store.get("status.current.arrangement") == "a"
    assert any("无法加载" in item["text"] for item in sup.store.get("status.log"))


def test_switch_crossfades_then_stops_old(sup, config):
    son, be = sup.sonification, sup.backend
    sup.switch(arrangement("a", control=[1, 2]))
    son.on_beat(beat(0, 1.0))
    assert sup.perception.interpreter._control_mask[[1, 2]].all()
    old = son.active
    sup.switch(arrangement("b", synth="bell"))
    son.on_beat(beat(1, 2.0))
    assert son.active.arrangement.id == "b"
    assert len(son.instances) == 2 and old.retiring
    assert sup.perception.interpreter._control_mask is None
    son.on_beat(beat(2, 2.5))
    sw = sup.store.get("status.current.switching")
    assert sw["to"] == "b" and 0 < sw["progress"] < 1
    fade = config.sound.crossfade_seconds
    son.on_beat(beat(3, 2.0 + fade + 0.1))
    assert [i.arrangement.id for i in son.instances] == ["b"]
    son.on_beat(beat(4, 2.0 + fade + 0.5))
    assert sup.store.get("status.current.switching") is None
    assert [c.args["instance"] for c in be.of_kind("free_mix")] == [old.id]


def test_mode_error_keeps_previous_intent(sup):
    son, be = sup.sonification, sup.backend
    sup.switch(arrangement())
    press(sup, 0.0, [5])
    press(sup, 0.1, [5])
    son.on_beat(beat(0, 1.0))
    son.active.mode.fail = True
    be.clear()
    son.on_beat(beat(1, 1.1))
    son.on_beat(beat(2, 1.2))
    assert be.of_kind("release_voice") == []   # 持续声部保持
    errors = [i for i in sup.store.get("status.log") if i["level"] == "error"]
    assert len(errors) == 1
    son.active.mode.fail = False
    son.on_beat(beat(3, 1.3))
    assert sup.store.get("status.log")[0]["text"].endswith("恢复正常")


def test_engine_status_published(sup):
    sup.switch(arrangement())
    sup.sonification.on_beat(beat(0, 1.0))
    st = sup.store.get("status.audio.engine")
    assert st["budget"] == 48 and st["voices"] == 0
