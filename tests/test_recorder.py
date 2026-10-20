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
    s.catalog.play("kyoto")
    return s


def settled(sup, timeout=3.0):
    """等录制的写文件线程把收尾做完（录制信息、关闭文件、刷新录制列表都在那个线程里）。"""
    import threading
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and any(t.name == "session-writer" for t in threading.enumerate()):
        time.sleep(0.01)


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
    beats(sup, 3.4, 4.17)
    assert sup.lights.system["recording"].alpha.min() == 1.0      # 打板：整圈全亮
    assert sup.store.get("status.recording")["flash"] is True
    # 打板在按下后 3 秒，录音也正好从这一刻开始；提示音在录音节点之后建立，不进录音
    assert sup.backend.of_kind("slate")[0].at == pytest.approx(1.1 + 3.0, abs=0.02)
    assert sup.backend.of_kind("start_recording")[0].at == sup.backend.of_kind("slate")[0].at
    kinds = [c.kind for c in sup.backend.commands]
    assert kinds.index("start_recording") < kinds.index("slate")
    for t in (1.2, 1.29):
        sup.perception.feed(sup.virtual.frame(t=t))   # 产生压力图与事件
    beats(sup, 4.17, 5.0)
    assert "recording" not in sup.lights.system
    assert sup.store.get("status.recording")["state"] == "recording"
    rec.request_stop()
    beats(sup, 5.0, 5.1)
    settled(sup)
    assert sup.store.get("status.recording") == {"state": "idle"}
    (item,) = sup.store.get("catalog.recordings")
    assert item["title"] == "京都岚山" and item["audio"] is False
    folder = rec.folder_of(item["name"])
    assert folder.name.endswith("_kyoto")
    info = json.loads((folder / "info.json").read_text())
    assert info["slateOffsetSeconds"] == 0.0 and info["stopReason"] == "user"
    assert info["duration"] == pytest.approx(5.0 - 4.1, abs=0.05)               # 从打板算起
    assert info["settings"]["sound"]["volume"] == 0.8
    assert info["files"] == ["session.jsonl", "info.json"]
    assert not (folder / "stems").exists()                        # 没有音频时不建分轨目录
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
    monkeypatch.setattr(rec, "bytes_per_second", lambda stems=None: 1_000_000)
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
    settled(sup)
    name = sup.store.get("catalog.recordings")[0]["name"]
    client = TestClient(create_app(sup.control, console_dist=None))
    r = client.get(f"/api/recordings/{name}/download")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert sorted(zf.namelist()) == [f"{name}/info.json", f"{name}/session.jsonl"]
    assert client.get("/api/recordings/../../etc/download").status_code == 404
    assert client.get("/api/recordings/nope/download").status_code == 404
    assert client.get("/api/recordings").json()[0]["name"] == name


def test_delete_recording(sup):
    """删除一段录制：整个文件夹没了，列表跟着更新；正在录的那一段、不存在的、路径越界的都不能删。"""
    rec = sup.recorder
    client = TestClient(create_app(sup.control, console_dist=None))
    rec.request_start()
    beats(sup, 1.0, 1.1)
    name = rec.session.folder.name
    r = client.post(f"/api/recordings/{name}/delete")
    assert r.status_code == 409 and "正在录制" in r.json()["detail"]
    rec.request_stop()
    beats(sup, 1.1, 1.2)
    settled(sup)
    folder = rec.folder_of(name)
    assert client.post(f"/api/recordings/{name}/delete").json() == {"ok": True}
    assert not folder.exists()
    assert sup.store.get("catalog.recordings") == []
    assert any("删除了录制" in i["text"] for i in sup.store.get("status.log"))
    assert client.post(f"/api/recordings/{name}/delete").status_code == 404
    assert client.post("/api/recordings/..%2F..%2Fetc/delete").status_code == 404


def test_stop_during_countdown_does_not_precede_the_start(sup):
    """倒计时中就停止：录音节点在打板时刻才建立，停止不能排在它前面，否则会一直录下去。"""
    rec = sup.recorder
    rec.request_start()
    beats(sup, 1.0, 1.5)
    rec.request_stop()
    beats(sup, 1.5, 1.6)
    start = sup.backend.of_kind("start_recording")[0].at
    assert sup.backend.of_kind("stop_recording")[0].at >= start
    assert sup.store.get("status.recording") == {"state": "idle"}


def test_beat_thread_never_touches_the_disk(sup, monkeypatch):
    """开始、录制中、结束的每一拍都不建文件夹、不开文件、不写文件：存储卡忙时那会让演奏停顿好几秒。"""
    import builtins
    import pathlib
    import threading

    beat_thread = threading.current_thread()            # 测试里由这个线程推进节拍
    real_open, real_mkdir, real_write = builtins.open, pathlib.Path.mkdir, pathlib.Path.write_text

    def guard(real):
        def wrapped(*a, **kw):
            assert threading.current_thread() is not beat_thread, "节拍线程读写了存储卡"
            return real(*a, **kw)
        return wrapped

    rec = sup.recorder
    rec.request_start()                                 # 建文件夹在这里（调用方的线程）
    monkeypatch.setattr(builtins, "open", guard(real_open))
    monkeypatch.setattr(pathlib.Path, "mkdir", guard(real_mkdir))
    monkeypatch.setattr(pathlib.Path, "write_text", guard(real_write))
    beats(sup, 1.0, 4.6)                                # 倒计时、打板、录制中
    rec.request_stop()
    beats(sup, 4.6, 4.7)                                # 结束
    monkeypatch.undo()
    settled(sup)
    (item,) = sup.store.get("catalog.recordings")
    assert (rec.folder_of(item["name"]) / "info.json").exists()
