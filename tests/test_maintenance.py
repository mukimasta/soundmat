from fastapi.testclient import TestClient

from soundmat.control import create_app
from soundmat.maintenance import Maintenance
from soundmat.monitor.log import EventLog
from soundmat.store import Store


def test_restart_targets_run_systemctl_and_are_logged():
    store = Store()
    ran = []
    m = Maintenance(store, EventLog(store), systemd=True, run=ran.append)
    assert store.get("status.maintenance") == {"enabled": True}
    m.restart("sound")
    m.restart("program")
    m.restart("machine")
    assert ran == [["restart", "jackd.service", "soundmat-scsynth.service"], ["restart", "soundmat.service"], ["reboot"]]
    assert store.get("status.log")[0]["text"] == "从控制台重启机器"


def test_restart_endpoint_refuses_off_device_and_unknown_targets(make_sup):
    sup = make_sup()                                   # 开发机上：不在 systemd 下
    client = TestClient(create_app(sup.control, console_dist=None))
    r = client.post("/api/system/restart", json={"target": "sound"})
    assert r.status_code == 409 and "只有装置上" in r.json()["detail"]
    sup.maintenance.enabled = True
    sup.maintenance.run = lambda args: None
    assert client.post("/api/system/restart", json={"target": "program"}).status_code == 202
    assert client.post("/api/system/restart", json={"target": "everything"}).status_code == 422
