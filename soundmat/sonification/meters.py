"""电平条：控制台垫面页下方每一层声音的电平（CONSOLE「垫面」、ARRANGEMENTS「电平条」）。

每根电平条对应编排里的一层声音，只显示这一层有多响，不分左右声道（方位由垫面上石头的位置表达）。
电平条分两组，控制台上靠间距分开：

- ``background``：不靠放石头、自己在走的部分，例如 Jam 的和声铺底和鼓；
- ``placed``：由放置的石头触发的部分，通常每个发声的环一根。

编排可以在 ``[meters]`` 里声明：

    [[meters.background]]
    label = "鼓"
    buses = ["drums"]        # 一根条可以对应多条总线，电平取最大值
    color = "#8A847A"        # 可省略

``placed`` 没有声明时，每个发声的环（混音结构里有这一环的总线、且不是控制区）一根，名字取
``ring_labels``；``background`` 没有声明时为空。所以拆分或增加背景元素只需要改编排文件。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from ..perception.zones import ZONES
from .mode import Arrangement, LoadError, LoadPlan

GROUPS = ("background", "placed")
_RING_BUS = re.compile(r"^ring(\d)$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True)
class Meter:
    id: str
    label: str
    group: str                       # background / placed
    buses: tuple[str, ...]
    ring: int | None = None          # 只对应一个环的总线时：用这一环的颜色
    color: str | None = None         # 编排指定的颜色 "#rrggbb"

    def to_json(self) -> dict:
        return {"id": self.id, "label": self.label, "group": self.group, "ring": self.ring, "color": self.color}


def _ring_of(buses: tuple[str, ...]) -> int | None:
    if len(buses) == 1:
        m = _RING_BUS.match(buses[0])
        if m:
            return int(m.group(1))
    return None


def _parse(group: str, items: Any, plan: LoadPlan) -> list[Meter]:
    if not isinstance(items, list):
        raise LoadError(f"meters.{group} 应是一组 [[meters.{group}]]")
    out = []
    for i, item in enumerate(items):
        where = f"meters.{group} 第 {i + 1} 项"
        if not isinstance(item, Mapping):
            raise LoadError(f"{where} 应是一个表")
        unknown = set(item) - {"label", "buses", "color"}
        if unknown:
            raise LoadError(f"{where} 有未知的项：{', '.join(sorted(unknown))}")
        label = item.get("label")
        if not isinstance(label, str) or not label:
            raise LoadError(f"{where} 缺少 label")
        buses = item.get("buses")
        if isinstance(buses, str):
            buses = [buses]
        if not isinstance(buses, list) or not buses or not all(isinstance(b, str) for b in buses):
            raise LoadError(f"{where}（{label}）的 buses 应是一组总线名")
        missing = [b for b in buses if b not in plan.buses]
        if missing:
            raise LoadError(f"{where}（{label}）引用了混音结构里没有的总线：{', '.join(missing)}")
        color = item.get("color")
        if color is not None and not (isinstance(color, str) and _COLOR.match(color)):
            raise LoadError(f"{where}（{label}）的 color 应写成 #rrggbb")
        bt = tuple(buses)
        out.append(Meter(f"{group}.{i}", label, group, bt, _ring_of(bt), color))
    return out


def _default_placed(arrangement: Arrangement, plan: LoadPlan) -> list[Meter]:
    control_rings = {ZONES[z].ring for z in plan.control_zones}
    out = []
    for r in range(8):
        bus = f"ring{r}"
        if bus not in plan.buses or r in control_rings:
            continue
        label = arrangement.ring_labels[r] if r < len(arrangement.ring_labels) else f"第 {r} 环"
        out.append(Meter(f"placed.{r}", label, "placed", (bus,), r))
    return out


def resolve_meters(arrangement: Arrangement, plan: LoadPlan) -> tuple[Meter, ...]:
    """按编排的 [meters] 声明和默认规则得到电平条，背景组在前。声明有误时抛出 ``LoadError``。"""
    spec = arrangement.meters or {}
    unknown = set(spec) - set(GROUPS)
    if unknown:
        raise LoadError(f"meters 只能有 background 和 placed，多了：{', '.join(sorted(unknown))}")
    background = _parse("background", spec["background"], plan) if "background" in spec else []
    placed = _parse("placed", spec["placed"], plan) if "placed" in spec else _default_placed(arrangement, plan)
    return tuple(background + placed)
