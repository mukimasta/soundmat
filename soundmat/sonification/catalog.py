"""编排目录：读取全部编排，检查各自引用的素材，写入状态中心供控制台列出；按标识开始演奏。"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..monitor.log import EventLog
from ..store import Store
from . import Sonification
from .arrangements import ARRANGEMENTS_DIR, discover
from .mode import Arrangement, LoadError

if TYPE_CHECKING:
    from ..sound.assets import AssetLibrary


class Catalog:
    def __init__(self, store: Store, events: EventLog, sonification: Sonification, assets: "AssetLibrary",
                 folder: Path = ARRANGEMENTS_DIR):
        self.state = store.writer("catalog.arrangements")
        self.events = events
        self.sonification = sonification
        self.assets = assets
        self.folder = folder
        self.arrangements: dict[str, Arrangement] = {}
        self.refresh()

    def refresh(self) -> None:
        """重新读取全部编排（例如换了声音素材库之后），检查各自引用的素材是否齐全。"""
        found, errors = discover(self.folder)
        for e in errors:
            self.events.warning(e)
        self.arrangements = found
        items = []
        for a in found.values():
            missing: list[str] = []
            error = None
            try:
                missing = self.assets.missing(self.sonification.prepare(a).plan.assets)
            except LoadError as e:
                error = str(e)
            items.append({
                "id": a.id, "title": a.title, "mode": a.mode, "modeLabel": a.mode_label,
                "description": a.description, "ringLabels": list(a.ring_labels),
                "missing": missing, "error": error,
            })
        self.state.set("catalog.arrangements", items)

    def play(self, arrangement_id: str) -> None:
        """切换到一份编排；没有这份编排或加载失败时抛出 ``LoadError``。"""
        a = self.arrangements.get(arrangement_id)
        if a is None:
            raise LoadError(f"没有标识为 {arrangement_id} 的编排")
        self.sonification.play(a)

    def play_default(self, default_id: str | None) -> None:
        """开机后进入默认编排；它不存在时用第一份。"""
        first = default_id if default_id in self.arrangements else next(iter(self.arrangements), None)
        if first is None:
            self.events.error("没有可用的编排")
            return
        if first != default_id:
            self.events.warning(f"默认编排 {default_id} 不存在，改用 {first}")
        try:
            self.play(first)
        except LoadError:
            pass          # 已经写进最近的记录
