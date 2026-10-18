from soundmat.store import Store


def test_set_get_and_notify_only_on_change():
    s = Store({"a": {"b": 1}})
    seen = []
    unsub = s.subscribe(seen.append)
    s.set("a.b", 1)
    s.set("a.c.d", "x")
    s.update({"a.b": 2, "e": [1]})
    assert seen == [[("a.c.d", "x")], [("a.b", 2), ("e", [1])]]
    assert s.get("a.c") == {"d": "x"}
    assert s.get("nope.x", 5) == 5
    unsub()
    s.set("a.b", 3)
    assert len(seen) == 2


def test_snapshot_is_a_copy():
    s = Store({"a": {"b": [1]}})
    snap = s.snapshot()
    snap["a"]["b"].append(2)
    assert s.get("a.b") == [1]


def test_each_branch_has_one_writer():
    import pytest

    from soundmat.store import Store

    store = Store()
    rec = store.writer("status.recording")
    rec.set("status.recording.state", "idle")
    assert store.get("status.recording") == {"state": "idle"}
    with pytest.raises(RuntimeError):
        store.writer("status.recording")              # 一段只能有一个写入者
    with pytest.raises(PermissionError):
        store.set("status.recording.state", "x")      # 被领取的段不能直接写
    with pytest.raises(PermissionError):
        store.set("status", {})                       # 也不能连同上级一起覆盖
    with pytest.raises(PermissionError):
        rec.set("status.update", {})                  # 写入者只能写自己的段
    with pytest.raises(KeyError):
        store.writer("status.nowhere")                # 只能领取登记过的段
    store.set("status.update", {"state": "idle"})     # 没有被领取的段照常可写（测试里常用）
