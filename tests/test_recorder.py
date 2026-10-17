import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from soundmat.clock import Beat
from soundmat.control import create_app
from soundmat.perception.zones import zone
from soundmat.recorder import RecordingError


@pytest.fixture
def sup(make_sup, tmp_path, monkeypatch):
    monkeypatch.setenv("SOUNDMAT_SOUND", str(tmp_path / "no-sound"))
    s = make_sup(monitor=False)
    s.play("kyoto")
    return s


def beats(sup, t0, t1, dt=1 / 60):
    i, t = 0, t0
    while t < t1:
        sup.sonification.on_beat(Beat(i, t, dt))
        i += 1
        t = t0 + i * dt


def test_full_recording_cycle(sup):
    rec = sup.recorder
    beats(sup, 1.0, 1.1)
    sup.virtual.set(zone(3, 0).index, True)
    rec.request_start()
    beats(sup, 1.1, 1.5)
    st = sup.store.get("status.recording")
    assert st["state"] == "countdown" and st["count"] == 3 and st["audio"] is False
    layer = sup.lights.system["recording"]
    assert layer.alpha.sum() == pytest.approx(0.9 * 108)          # 三段全亮
    beats(sup, 1.5, 3.4)
    assert sup.lights.system["recording"].alpha.sum() == pytest.approx(0.9 * 36)   # 剩一段
    assert sup.store.get("status.recording")["count"] == 1
    beats(sup, 3.4, 4.37)
    assert sup.lights.system["recording"].alpha.min() == 1.0      # 打板：整圈全亮
    assert sup.store.get("status.recording")["flash"] is True
    assert sup.backend.of_kind("slate")[0].at == pytest.approx(1.1 + 0.2 + 3.0, abs=0.02)
    for t in (1.2, 1.25):
        sup.perception.feed(sup.virtual.frame(t=t))   # 产生压力图与事件
    beats(sup, 4.37, 5.0)
    assert "recording" not in sup.lights.system
    assert sup.store.get("status.recording")["state"] == "recording"
    rec.request_stop()
    beats(sup, 5.0, 5.1)
    assert sup.store.get("status.recording") == {"state": "idle"}
    (item,) = sup.store.get("catalog.recordings")
    assert item["title"] == "京都岚山" and item["audio"] is False
    folder = rec.folder_of(item["name"])
    assert folder.name.endswith("_kyoto")
    info = json.loads((folder / "info.json").read_text())
    assert info["slateOffsetSeconds"] == 3.0 and info["stopReason"] == "user"
    assert info["duration"] == pytest.approx(5.0 - 1.3, abs=0.05)
    assert info["settings"]["sound"]["volume"] == 0.8
    types = [json.loads(l)["type"] for l in (folder / "session.jsonl").read_text().splitlines()]
    assert types[0] == "start" and types[-1] == "stop"
    assert {"pressure", "sound", "slate", "event"} <= set(types)
    assert sup.backend.of_kind("start_recording")[0].args["files"]["master"].endswith("master.wav")


def test_refuses_when_disk_too_small_and_auto_stops(sup, monkeypatch):
    rec = sup.recorder
    monkeypatch.setattr(rec, "free_bytes", lambda: 10 * 1024 * 1024)
    with pytest.raises(RecordingError, match="剩余空间"):
        rec.request_start()
    client = TestClient(create_app(sup.control, console_dist=None))
    r = client.post("/api/recording/start")
    assert r.status_code == 409 and "剩余空间" in r.json()["detail"]

    monkeypatch.setattr(rec, "free_bytes", lambda: 10**12)
    monkeypatch.setattr(rec, "bytes_per_second", lambda stems: 1_000_000)
    rec.request_start()
    beats(sup, 1.0, 5.0)
    monkeypatch.setattr(rec, "free_bytes", lambda: 1000)
    rec.session.audio = True        # 模拟有音频文件在写
    rec._was_audio_active = False
    beats(sup, 5.0, 6.0)
    assert sup.store.get("status.recording") == {"state": "idle"}
    assert any("存储空间将尽" in i["text"] for i in sup.store.get("status.log"))


def test_double_start_and_download_zip(sup):
    rec = sup.recorder
    rec.request_start()
    beats(sup, 1.0, 1.1)
    with pytest.raises(RecordingError, match="已经在录制"):
        rec.request_start()
    rec.request_stop()
    beats(sup, 1.1, 1.2)
    name = sup.store.get("catalog.recordings")[0]["name"]
    client = TestClient(create_app(sup.control, console_dist=None))
    r = client.get(f"/api/recordings/{name}/download")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert sorted(zf.namelist()) == [f"{name}/info.json", f"{name}/session.jsonl"]
    assert client.get("/api/recordings/../../etc/download").status_code == 404
    assert client.get("/api/recordings/nope/download").status_code == 404
    assert client.get("/api/recordings").json()[0]["name"] == name
