
import pytest

from soundmat.monitor import Monitor, Probes, Sources
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
    # Pi 3B 上第一版的写法：选项和值连写
    jack = P.parse_jack_args(["/usr/bin/jackd", "-P75", "-t2000", "-dalsa", "-dhw:Audio", "-r44100", "-p2048", "-n2"])
    assert jack == {"running": True, "device": "hw:Audio", "rate": 44100, "period": 2048, "periods": 2}
    assert P.parse_jack_args(["jackd", "-P75"])["device"] is None


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
        self.synth_late = 0
        self.network = {"name": "soundmat", "address": "172.20.10.3", "tailscale": "Running"}
        self.restarts = None
        self.version = {"commit": "abc1234", "deployedAt": "2026-10-17T15:00", "dirty": None, "source": "deploy"}
        self.clients = 2

    def probes(self):
        return Probes(jack=lambda: self.jack, cards=lambda: self.cards, xruns=lambda since: self.xruns,
                      synth_late=lambda: self.synth_late, clock=lambda: True,
                      machine=lambda d: {"host": "soundmat-pi", "tempC": 49.0}, network=lambda: self.network,
                      restarts=lambda svc: self.restarts, version=lambda root: self.version,
                      ap_clients=lambda iface: self.clients, platform_linux=True)


class Runtime:
    """各模块交给系统监测的运行数据（测试里手动设置）。"""

    def __init__(self):
        self.mat = {"source": "controller", "connected": True, "fps": 58.6}
        self.counts = {"stalls": 0, "late": 0, "yields": 0, "rejected": 0}
        self.lag = 0.0
        self.root = None
        self.bps = 0

    def rates(self):
        return {"beat": {"actual": 60.0, "expected": 60.0}}

    def counters(self):
        return dict(self.counts)

    def bytes_per_second(self):
        return self.bps


@pytest.fixture
def rig(config, tmp_path):
    store = Store({"status": {"assets": {"missing": []}}})
    fake = Fake()
    synth = {"online": True, "synthdefsLoaded": True, "nominalSampleRate": 48000.0, "avgCPU": 22.0, "peakCPU": 30.0}
    rt = Runtime()
    rt.root = tmp_path
    mon = Monitor(config, store, EventLog(store), tmp_path, probes_=fake.probes(), sources=Sources(
        synth=lambda: synth, channels=lambda: 2, mat=lambda: rt.mat, rates=[rt], counters=[rt],
        beat_lag=lambda: rt.lag, storage=rt))
    mon.rt = rt
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
    (lambda f, s, st: st.set("status.assets.missing", ["a", "b"]), "warn", "缺少 2 个声音素材"),
    (lambda f, s, st: s.update(peakCPU=91.0), "warn", "峰值 91%"),
    (lambda f, s, st: setattr(f, "xruns", 3), "warn", "卡顿 3 次"),
    (lambda f, s, st: setattr(f, "synth_late", 12), "warn", "12 条指令收到得太晚"),
])
def test_sound_rules(rig, change, level, text):
    mon, store, fake, synth = rig
    change(fake, synth, store)
    h = mon.step(0)
    assert h["sound"]["level"] == level and text in h["sound"]["reason"]
    assert h["overall"] == level


def test_mat_and_network_rules(rig):
    mon, store, fake, synth = rig
    mon.rt.mat = {"source": "controller", "connected": False, "problem": "没有找到控制器的 USB 串口"}
    h = mon.step(0)
    assert h["mat"] == {"level": "error", "reason": "没有找到控制器的 USB 串口"}
    assert store.get("status.mat.problem") == "没有找到控制器的 USB 串口"
    mon.rt.mat = {"source": "controller", "connected": True, "fps": 12.0}
    assert mon.step(1)["mat"]["level"] == "warn"
    mon.rt.mat = {"source": "virtual"}
    assert mon.step(2)["mat"]["level"] == "ok"
    fake.network = {"name": None, "address": None}
    mon._next_slow = 0
    assert mon.step(20)["net"]["level"] == "warn"


def test_no_synth_is_unknown(config, tmp_path):
    store = Store()
    mon = Monitor(config, store, EventLog(store), tmp_path, probes_=Fake().probes())
    assert mon.step(0)["sound"]["level"] == "unknown"


def test_neigh_and_network_kind():
    text = ("10.42.0.23 lladdr 3a:11:22:33:44:55 REACHABLE\n"
            "10.42.0.31 lladdr 3a:11:22:33:44:66 STALE\n"
            "10.42.0.40 FAILED\n")
    assert P.parse_neigh(text) == 2
    kind = lambda name, t="wifi": P.network_kind({"name": name, "type": t}, "phone-hotspot", "soundmat-ap")
    assert kind("phone-hotspot") == "phoneHotspot"
    assert kind("soundmat-ap") == "selfHotspot"
    assert kind("netplan-wlan0-Avocado") == "external"
    assert kind("netplan-eth0", "ethernet") == "wired"
    assert kind(None) is None


def test_version_prefers_deploy_file(tmp_path):
    (tmp_path / "VERSION").write_text("2d09273\n2026-10-17T15:00:00-07:00\n")
    assert P.version(tmp_path) == {"commit": "2d09273", "deployedAt": "2026-10-17T15:00:00-07:00",
                                   "branch": None, "dirty": None, "source": "deploy"}
    (tmp_path / "VERSION").write_text("2d09273\n2026-10-17T15:00:00-07:00\nmaster\n")
    assert P.version(tmp_path)["branch"] == "master"
    assert P.version(tmp_path / "nowhere") is None


def test_restarts_unknown_outside_systemd(monkeypatch):
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    assert P.systemd_restarts("soundmat.service") is None


def test_program_network_storage_and_rates_published(rig, tmp_path):
    mon, store, fake, synth = rig
    fake.network = {"name": "soundmat-ap", "type": "wifi", "address": "10.42.0.1", "tailscale": None}
    mon.rt.root, mon.rt.bps = tmp_path / "recordings", 48000 * 2 * 3
    mon.step(0)
    assert store.get("status.network.kind") == "selfHotspot"
    assert store.get("status.network.apClients") == 2
    assert store.get("status.program.version.commit") == "abc1234"
    assert store.get("status.program.restarts") is None
    assert store.get("status.rates.beat") == {"actual": 60.0, "expected": 60.0}
    st = store.get("status.storage")
    assert st["freeGB"] > 0 and st["minutes"] > 0
    mon.rt.root, mon.rt.bps = tmp_path, 0
    mon.step(1)
    assert store.get("status.storage.minutes") is None          # 不录音频时无法换算成分钟


def test_recent_stalls_and_late_events_need_attention(rig):
    """节拍晚到超过迟到容忍度（卡住）或定时事件迟到才需要注意。"""
    mon, store, fake, synth = rig
    counts = mon.rt.counts
    mon.rt.lag = 0.012
    assert mon.step(0)["sound"]["level"] == "ok"                # 启动以来的累计数不算
    counts["stalls"] = 2
    assert mon.step(0.5)["sound"]["level"] == "ok"              # 卡住两次：不提示
    assert store.get("status.timing.stallsRecent") == 2
    assert store.get("status.timing.maxLagMs") == 12.0
    counts["stalls"] = 5
    h = mon.step(1)
    assert h["sound"]["level"] == "warn" and "5 次晚到超过 50 ms" in h["sound"]["reason"]
    assert store.get("status.timing.stallsAttention") is True
    counts["late"] = 2
    mon.step(30)
    h = mon.step(62)                                            # 一分钟之后：最近 1 分钟里没有新的卡住
    assert store.get("status.timing.stallsRecent") == 0
    assert h["sound"]["level"] == "warn" and "迟到" in h["sound"]["reason"]
    h = mon.step(95)
    assert h["sound"]["level"] == "ok"


def test_recent_restart_needs_attention(rig):
    mon, store, fake, synth = rig
    fake.restarts = 2
    h = mon.step(0)
    assert h["sound"]["level"] == "warn" and "自动重启" in h["sound"]["reason"]
    mon.started -= 7200                                         # 已经稳定运行了两小时
    mon._next_slow = 0
    assert mon.step(20)["sound"]["level"] == "ok"



def test_restart_planned_by_update_is_not_an_error(rig, tmp_path):
    """更新切换版本后的重启是有意的：systemd 的重启计数会增加，但不算出错。"""
    import json as _json
    import time as _time
    mon, store, fake, synth = rig
    fake.restarts = 2
    (mon.data_dir / "update.json").write_text(_json.dumps({"plannedAt": _time.time() - 3}))
    h = mon.step(0)
    assert h["sound"]["level"] == "ok"
    assert store.get("status.program.plannedStart") is True


def test_program_and_machine_cpu(rig):
    """主机程序 CPU 按单核算（两次采集之间的增量），整机 CPU 是所有核的平均；持续占满单核需要注意。"""
    mon, store, fake, synth = rig
    clock = {"cpu": 100.0, "busy": 1000, "total": 10000}
    mon.probes.process_cpu = lambda: clock["cpu"]
    mon.probes.system_cpu = lambda: (clock["busy"], clock["total"])
    mon.step(0)
    assert store.get("status.machine.programCpu") is None          # 第一次没有增量
    clock.update(cpu=100.58, busy=1020, total=10100)
    mon.step(1)
    assert store.get("status.machine.programCpu") == 58.0
    assert store.get("status.machine.cpu") == 20.0
    assert store.get("status.health.sound.level") == "ok"
    for i in range(2, 9):
        clock["cpu"] += 0.95
        h = mon.step(i)
    assert h["sound"]["level"] == "warn" and "占满了一个 CPU 核" in h["sound"]["reason"]
    assert store.get("status.machine.programCpuHistory")[-1] == 95.0


def test_xruns_counted_since_the_later_start(rig):
    """卡顿从主机程序和 JACK 里较晚的那次启动算起、最长一小时：重启之前的卡顿不算作现在的问题。"""
    import time as _time

    mon, store, fake, synth = rig
    asked = []
    mon.probes.xruns = lambda since: asked.append(since) or 4
    fake.jack["startedAt"] = _time.time() - 120                  # JACK 两分钟前重启过
    h = mon.step(0)
    assert asked[-1] == pytest.approx(fake.jack["startedAt"])
    assert store.get("status.audio.xrunsSinceStart") is True
    assert h["sound"]["reason"] == "启动以来音频卡顿 4 次"
    fake.jack["startedAt"] = _time.time() - 7200
    mon.started_wall -= 7200                                     # 都已运行两小时：只看最近一小时
    mon._next_slow = 0
    h = mon.step(20)
    assert asked[-1] == pytest.approx(_time.time() - 3600, abs=5)
    assert h["sound"]["reason"] == "最近一小时音频卡顿 4 次"


def test_clock_status_file(tmp_path):
    """开机服务写下的结论：synced / unsynced；没有文件时未知。"""
    f = tmp_path / "clock"
    assert P.clock_status(str(f)) is None
    f.write_text("synced 28\n")
    assert P.clock_status(str(f)) is True
    f.write_text("unsynced 20\n")
    assert P.clock_status(str(f)) is False
