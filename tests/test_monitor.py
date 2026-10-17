from pathlib import Path

import pytest

from soundmat.monitor import Monitor, Probes
from soundmat.monitor.log import EventLog
from soundmat.monitor import probes as P
from soundmat.store import Store

CARDS = """ 0 [vc4hdmi0       ]: vc4-hdmi - vc4-hdmi-0
                      vc4-hdmi-0
 2 [Device         ]: USB-Audio - JCALLY JM6
                      JCALLY JM6 at usb-xhci-hcd.0-1, full speed
"""


def test_parse_cards_and_jack_device():
    cards = P.parse_cards(CARDS)
    assert [c["id"] for c in cards] == ["vc4hdmi0", "Device"]
    jack = P.parse_jack_args(["jackd", "-P70", "-d", "alsa", "-d", "hw:Device", "-r", "48000", "-p", "2048", "-n", "2"])
    assert jack == {"running": True, "device": "hw:Device", "rate": 48000, "period": 2048, "periods": 2}
    assert P.output_device(jack, cards) == {"name": "USB-Audio - JCALLY JM6", "usb": True}
    jack["device"] = "hw:2"
    assert P.output_device(jack, cards)["usb"] is True
    jack["device"] = "hw:0"
    assert P.output_device(jack, cards) == {"name": "vc4-hdmi - vc4-hdmi-0", "usb": False}
    assert P.parse_jack_args(["jackd", "-d", "dummy", "-r", "48000"])["device"] == "dummy"


def test_local_name_not_doubled():
    assert P.local_name("soundmat-pi") == "soundmat-pi.local"
    assert P.local_name("MacBook-Pro.local") == "MacBook-Pro.local"
    assert P.local_name(None) is None


def test_real_probes_do_not_crash(tmp_path):
    m = P.machine(tmp_path)
    assert m["host"] and m["diskFreeGB"] is not None
    n = P.network()
    assert "address" in n


class Fake:
    def __init__(self):
        self.jack = {"running": True, "device": "hw:2", "rate": 48000, "period": 2048, "periods": 2}
        self.cards = P.parse_cards(CARDS)
        self.xruns = 0
        self.network = {"name": "soundmat", "address": "172.20.10.3", "tailscale": "Running"}

    def probes(self):
        return Probes(jack=lambda: self.jack, cards=lambda: self.cards, xruns=lambda: self.xruns,
                      machine=lambda d: {"host": "soundmat-pi", "tempC": 49.0}, network=lambda: self.network,
                      platform_linux=True)


@pytest.fixture
def rig(config, tmp_path):
    store = Store({"status": {"mat": {"source": "controller", "connected": True, "fps": 58.6}, "audio": {"assets": {"missing": []}}}})
    fake = Fake()
    synth = {"online": True, "synthdefsLoaded": True, "nominalSampleRate": 48000.0, "avgCPU": 22.0, "peakCPU": 30.0}
    mon = Monitor(config, store, EventLog(store), tmp_path, synth_status=lambda: synth,
                  layout_channels=lambda: 2, probes_=fake.probes())
    return mon, store, fake, synth


def test_all_ok_and_dashboard_fields(rig):
    mon, store, fake, synth = rig
    h = mon.step(0)
    assert h["overall"] == "ok" and h["issues"] == []
    assert store.get("status.audio.outputDevice") == {"name": "USB-Audio - JCALLY JM6", "usb": True}
    assert store.get("status.audio.buffer") == {"period": 2048, "periods": 2, "driver": "JACK"}
    assert store.get("status.network.line") == "soundmat · soundmat-pi.local"
    assert store.get("status.network.localName") == "soundmat-pi.local"
    assert store.get("status.audio.loadHistory") == [22.0]


def test_hdmi_output_is_an_error_with_reason_and_logged_once(rig):
    mon, store, fake, synth = rig
    fake.jack["device"] = "hw:0"
    h = mon.step(0)
    assert h["sound"]["level"] == "error"
    assert h["sound"]["reason"].startswith("合成器服务没有使用 USB 声卡，当前输出到 vc4-hdmi - vc4-hdmi-0")
    mon.step(1)
    errors = [i for i in store.get("status.log") if i["level"] == "error"]
    assert len(errors) == 1
    fake.jack["device"] = "hw:2"
    mon.step(2)
    assert store.get("status.log")[0]["text"] == "声音：恢复正常"


@pytest.mark.parametrize("change, level, text", [
    (lambda f, s, st: s.update(online=False, everOnline=True), "error", "没有响应"),
    (lambda f, s, st: s.update(online=False), "unknown", "正在连接"),
    (lambda f, s, st: s.update(synthdefsLoaded=False), "error", "没有加载音色"),
    (lambda f, s, st: f.jack.update(running=False), "error", "JACK"),
    (lambda f, s, st: s.update(nominalSampleRate=44100.0), "warn", "44.1 kHz，期望 48 kHz"),
    (lambda f, s, st: st.set("status.audio.assets.missing", ["a", "b"]), "warn", "缺少 2 个声音素材"),
    (lambda f, s, st: s.update(peakCPU=91.0), "warn", "峰值 91%"),
    (lambda f, s, st: setattr(f, "xruns", 3), "warn", "卡顿 3 次"),
])
def test_sound_rules(rig, change, level, text):
    mon, store, fake, synth = rig
    change(fake, synth, store)
    h = mon.step(0)
    assert h["sound"]["level"] == level and text in h["sound"]["reason"]
    assert h["overall"] == level


def test_mat_and_network_rules(rig):
    mon, store, fake, synth = rig
    store.set("status.mat", {"source": "controller", "connected": False, "problem": "没有找到控制器的 USB 串口"})
    h = mon.step(0)
    assert h["mat"] == {"level": "error", "reason": "没有找到控制器的 USB 串口"}
    store.set("status.mat", {"source": "controller", "connected": True, "fps": 12.0})
    assert mon.step(1)["mat"]["level"] == "warn"
    store.set("status.mat", {"source": "virtual"})
    assert mon.step(2)["mat"]["level"] == "ok"
    fake.network = {"name": None, "address": None}
    mon._next_slow = 0
    assert mon.step(20)["net"]["level"] == "warn"


def test_no_synth_is_unknown(config, tmp_path):
    store = Store()
    mon = Monitor(config, store, EventLog(store), tmp_path, synth_status=lambda: None,
                  layout_channels=lambda: 2, probes_=Fake().probes())
    assert mon.step(0)["sound"]["level"] == "unknown"
