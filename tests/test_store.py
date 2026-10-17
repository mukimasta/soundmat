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
