from fastapi.testclient import TestClient

from soundmat.clock import Beat
from soundmat.control import create_app


def test_catalog_reports_missing_assets_without_library(make_sup, tmp_path, monkeypatch):
    monkeypatch.setenv("SOUNDMAT_SOUND", str(tmp_path / "no-sound"))
    sup = make_sup()
    (item,) = [a for a in sup.store.get("catalog.arrangements") if a["id"] == "kyoto"]
    assert item["title"] == "京都岚山" and len(item["missing"]) == 14 and item["error"] is None


def test_default_arrangement_plays_and_api(make_sup, tmp_path, monkeypatch):
    monkeypatch.setenv("SOUNDMAT_SOUND", str(tmp_path / "no-sound"))
    sup = make_sup()
    sup.start()
    sup.clock.stop()          # 手动推进节拍
    son = sup.sonification
    son.on_beat(Beat(0, 1.0, 1 / 60))
    assert sup.store.get("status.current.arrangement") == "kyoto"
    assert len(sup.store.get("status.audio.assets.missing")) == 14
    assert sup.backend.of_kind("set_master")[0].args["params"] == {"volume": 0.8}

    client = TestClient(create_app(sup.control, console_dist=None))
    assert client.post("/api/arrangements/nope/play").status_code == 422
    r = client.post("/api/settings", json={"changes": {"sound.volume": 0.3}})
    assert r.json() == {"applied": {"sound.volume": 0.3}}
    assert client.post("/api/settings", json={"changes": {"sound.volume": 3}}).status_code == 422
    son.on_beat(Beat(1, 1.1, 1 / 60))
    assert sup.backend.of_kind("set_master")[-1].args["params"] == {"volume": 0.3}
    client.post("/api/settings", json={"changes": {"sound.layout": "quad"}})
    son.on_beat(Beat(2, 1.2, 1 / 60))
    assert sup.backend.of_kind("create_mix")[-1].args["channels"] == 4
    assert client.post("/api/arrangements/kyoto/play").json() == {"ok": True}


def test_controller_end_to_end_with_fake_esp32(make_sup, tmp_path, monkeypatch):
    import time

    from soundmat.device import DeviceLink
    from soundmat.perception.zones import zone

    from fake_esp32 import FakeESP32

    monkeypatch.setenv("SOUNDMAT_SOUND", str(tmp_path / "no-sound"))
    esp = FakeESP32(boot_lines=1)
    holder = {}
    link = DeviceLink(lambda f: holder["sup"]._on_raw_frame(f), opener=lambda p: esp,
                      picker=lambda s: "/dev/fake")
    sup = make_sup(virtual=False, device=link)
    holder["sup"] = sup
    link._on_event = sup._device_event
    sup.start()
    try:
        esp.press(7 * 32 + 10, 3000)         # 接线 [7, 10] → 第 7 环第 25 区
        target = zone(7, 25).index
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and target not in sup.perception.snapshot.get().state.occupied:
            time.sleep(0.02)
        assert target in sup.perception.snapshot.get().state.occupied
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not esp.received:
            time.sleep(0.02)
        assert esp.received and esp.received[0].startswith(b"L:")
        time.sleep(0.6)
        st = sup.store.get("status.mat")
        assert st["connected"] and st["source"] == "controller" and st["fps"] > 0
    finally:
        sup.stop()


def test_test_tone_endpoint(make_sup, tmp_path, monkeypatch):
    from soundmat.clock import Beat

    monkeypatch.setenv("SOUNDMAT_SOUND", str(tmp_path / "no-sound"))
    sup = make_sup(monitor=False)
    client = TestClient(create_app(sup.control, console_dist=None))
    assert client.post("/api/audio/test-tone", json={"channel": 1}).json() == {"ok": True}
    assert client.post("/api/audio/test-tone", json={"channel": 2}).status_code == 422
    sup.sonification.on_beat(Beat(0, 1.0, 1 / 60))
    assert sup.backend.of_kind("test_tone")[0].args["channel"] == 1
