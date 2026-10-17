import pytest
from fastapi.testclient import TestClient

from soundmat.control import create_app



@pytest.fixture
def sup(make_sup):
    return make_sup()


def test_hello_then_mat_and_patch(sup):
    client = TestClient(create_app(sup.control, console_dist=None))
    with client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert len(hello["geometry"]) == 224
        assert hello["state"]["status"]["current"]["virtual"] is True
        assert any(r["label"] == "占用阈值" for r in hello["config"])

        r = client.post("/api/virtual/toggle", json={"zone": 50})
        assert r.json() == {"zone": 50, "stone": True}
        vm = sup.virtual
        sup.perception.feed(vm.frame(t=1.0))
        sup.perception.feed(vm.frame(t=1.1))
        sup.store.set("status.current.arrangement", "kyoto")

        got_mat = got_patch = False
        for _ in range(20):
            msg = ws.receive_json()
            if msg["type"] == "mat" and msg["occupied"] == [50]:
                assert msg["pressure"][50] == 500 and msg["source"] == "virtual"
                got_mat = True
            if msg["type"] == "patch":
                assert ["status.current.arrangement", "kyoto"] in msg["changes"]
                got_patch = True
            if got_mat and got_patch:
                break
        assert got_mat and got_patch


def test_virtual_endpoints(sup):
    client = TestClient(create_app(sup.control, console_dist=None))
    assert client.post("/api/virtual/toggle", json={"zone": 999}).status_code == 422
    client.post("/api/virtual/toggle", json={"zone": 1})
    assert sup.virtual.stones == {1}
    client.post("/api/virtual/clear")
    assert sup.virtual.stones == frozenset()
    assert len(client.get("/api/geometry").json()) == 224


def test_virtual_endpoints_refused_without_virtual_mat(make_sup):
    s = make_sup(virtual=False)
    client = TestClient(create_app(s.control, console_dist=None))
    assert client.post("/api/virtual/toggle", json={"zone": 1}).status_code == 409
    assert "控制台还没有构建" in client.get("/").text
