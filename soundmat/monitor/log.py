"""最近的警告和错误：保存在内存中，推给状态中心供看板显示（TECH_STACK「存储」）。"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque

from ..store import Store

log = logging.getLogger("soundmat")


class EventLog:
    def __init__(self, store: Store, path: str = "status.log", size: int = 30):
        self._store = store
        self._path = path
        self._lock = threading.Lock()
        self._items: deque[dict] = deque(maxlen=size)

    def _add(self, level: str, text: str) -> None:
        item = {"at": time.time(), "level": level, "text": text}
        with self._lock:
            if self._items and self._items[0]["text"] == text and self._items[0]["level"] == level:
                self._items[0] = {**item, "count": self._items[0].get("count", 1) + 1}
            else:
                self._items.appendleft(item)
            items = list(self._items)
        self._store.set(self._path, items)

    def info(self, text: str) -> None:
        log.info(text)
        self._add("info", text)

    def warning(self, text: str) -> None:
        log.warning(text)
        self._add("warning", text)

    def error(self, text: str) -> None:
        log.error(text)
        self._add("error", text)
