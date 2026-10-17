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
