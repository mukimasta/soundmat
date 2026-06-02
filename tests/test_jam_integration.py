"""端到端离线烟测：跑完整 JamApp 主循环（假 SC/OSC，无 scsynth）。

验证五层 + 桥 + 主循环串起来不抛异常，并真的产生 OSC 发声指令。
"""
import time

from soundmat import config
from soundmat.app import load_manifest
from soundmat.core.led.writer import LEDWriter
from soundmat.core.sensor.mock_reader import MockSensorReader
from soundmat.core.services import SharedServices
from soundmat.jam.app import JamApp


class FakeOSC:
    def __init__(self):
        self.synths = []      # (name, params)
        self.sets = []        # (node, params)
        self._id = 1000

    def alloc_id(self):
        self._id += 1
        return self._id

    def new_group(self, target=1, add_action=1):
        return self.alloc_id()

    def new_synth(self, name, params=None, *, target=1, add_action=0):
        nid = self.alloc_id()
        self.synths.append((name, dict(params or {})))
        return nid

    def set_node(self, node_id, **params):
        self.sets.append((node_id, params))

    def free_node(self, node_id):
        pass

    def deep_free_group(self, group_id):
        pass


class FakeSC:
    def __init__(self, osc):
        self.osc = osc

    def new_group(self, target=1, add_action=1):
        return self.osc.new_group()

    def free_group(self, gid):
        pass


def _make_app():
    osc = FakeOSC()
    sc = FakeSC(osc)
    sensor = MockSensorReader()        # 手动注入模式（不起线程）
    leds = LEDWriter()                 # 无串口，虚拟
    services = SharedServices(sc=sc, sensor=sensor, leds=leds, osc=osc)
    manifest = load_manifest(config.DEFAULT_MANIFEST)
    app = JamApp(manifest, services)
    return app, osc, sensor


def test_jam_full_loop_offline():
    app, osc, sensor = _make_app()
    app.start()
    try:
        # master synth 应已 spawn
        assert any(name == "jam_master" for name, _ in osc.synths)

        # 放一颗旋律石（R7 wire slice 0）+ 控制石（R0 wire slice 0）；L sector 见 SECTOR_OFFSET
        sensor.inject([(7, 0), (0, 0)])
        # 让主循环跑一会，扫描线推进多圈，应触发和声/鼓/旋律
        time.sleep(1.0)

        names = [n for n, _ in osc.synths]
        assert "jam_chord_pad" in names, "应有和声 pad"
        assert "jam_marimba" in names, "R7 石头应触发 marimba"
        # 注：鼓曲式首段 A 为空（8 小节 ≈ 16s 静默渐入），1s 内本就无鼓，见 test_drum_engine_form

        # LED buffer 应为 108 路
        assert len(app.services.leds.latest()) == config.NUM_LEDS

        # status 正常
        st = app.status()
        assert st["mode"] == "jam" and st["playing"] in (True, False)
    finally:
        app.stop()
        sensor.stop()


def test_jam_lofi_param_sets_master():
    app, osc, sensor = _make_app()
    app.start()
    try:
        # 控制环加压 → master_fx 应 set_node 调 cutoff/drive
        sensor.inject([(0, 3), (1, 7)])
        time.sleep(0.3)
        assert any("cutoff" in p or "drive" in p for _, p in osc.sets), "Lo-Fi 应调 master 参数"
    finally:
        app.stop()
        sensor.stop()
