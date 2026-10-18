"""电平条：编排声明、默认规则、校验，以及运行管理按电平条发布电平。"""
import time

import pytest

from soundmat.perception.zones import ring_indices
from soundmat.sonification.meters import resolve_meters
from soundmat.sonification.mode import Arrangement, LoadError, LoadPlan

LABELS = ("控制", "控制", "低音", "贝斯", "拨弦", "暗电钢", "电钢", "马林巴")
JAM_PLAN = LoadPlan(
    buses=tuple(f"ring{r}" for r in range(8)) + ("harmony", "drums"),
    control_zones=frozenset(list(ring_indices(0)) + list(ring_indices(1))),
)


def arr(meters=None, labels=LABELS):
    return Arrangement(id="a", title="A", mode="jam", ring_labels=labels, meters=meters or {})


def test_default_one_meter_per_sounding_ring_skipping_control_rings():
    ms = resolve_meters(arr(), JAM_PLAN)
    assert [m.label for m in ms] == list(LABELS[2:])
    assert all(m.group == "placed" for m in ms)
    assert [m.ring for m in ms] == [2, 3, 4, 5, 6, 7]


def test_default_without_control_zones_or_labels():
    ms = resolve_meters(arr(labels=()), LoadPlan())
    assert len(ms) == 8 and ms[0].label == "第 0 环"


def test_declared_background_comes_first_and_placed_keeps_default():
    spec = {"background": [{"label": "和声", "buses": ["harmony"]},
                           {"label": "鼓", "buses": ["drums"], "color": "#8A847A"}]}
    ms = resolve_meters(arr(spec), JAM_PLAN)
    assert [(m.group, m.label) for m in ms[:2]] == [("background", "和声"), ("background", "鼓")]
    assert ms[1].color == "#8A847A" and ms[0].ring is None
    assert [m.group for m in ms[2:]] == ["placed"] * 6


def test_one_meter_can_cover_several_buses():
    spec = {"background": [{"label": "鼓", "buses": ["drums", "harmony"]}],
            "placed": [{"label": "外圈", "buses": "ring7"}]}
    ms = resolve_meters(arr(spec), JAM_PLAN)
    assert ms[0].buses == ("drums", "harmony")
    assert ms[1].buses == ("ring7",) and ms[1].ring == 7
    assert len(ms) == 2


@pytest.mark.parametrize("spec, msg", [
    ({"background": [{"label": "鼓", "buses": ["kick"]}]}, "没有的总线"),
    ({"background": [{"buses": ["drums"]}]}, "缺少 label"),
    ({"background": [{"label": "鼓", "buses": []}]}, "buses"),
    ({"background": [{"label": "鼓", "buses": ["drums"], "color": "red"}]}, "#rrggbb"),
    ({"background": [{"label": "鼓", "buses": ["drums"], "gain": 1}]}, "未知的项"),
    ({"foreground": []}, "background 和 placed"),
    ({"background": {"label": "鼓"}}, "应是一组"),
])
def test_invalid_declarations(spec, msg):
    with pytest.raises(LoadError, match=msg):
        resolve_meters(arr(spec), JAM_PLAN)


def test_shipped_arrangements(make_sup):
    sup = make_sup()
    by_id = {a["id"]: a for a in sup.store.get("catalog.arrangements")}
    assert by_id["lofi_1"]["error"] is None and by_id["kyoto"]["error"] is None


def test_supervisor_publishes_meter_definitions_and_levels(make_sup):
    sup = make_sup()
    sup.start()
    sup.catalog.play("lofi_1")
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and sup.store.get("status.current.arrangement") != "lofi_1":
        time.sleep(0.05)
    meters = sup.store.get("status.current.meters")
    assert [m["label"] for m in meters] == ["和声", "鼓", "低音", "贝斯", "拨弦", "暗电钢", "电钢", "马林巴"]
    assert meters[0] == {"id": "background.0", "label": "和声", "group": "background", "ring": None, "color": None}
    assert meters[2]["ring"] == 2
    lv = None
    while time.monotonic() < deadline:
        lv = sup.sonification.levels.get()
        if lv and len(lv["meters"]) == len(meters):
            break
        time.sleep(0.05)
    assert lv is not None and len(lv["meters"]) == len(meters)
    assert set(lv) == {"output", "meters"}
