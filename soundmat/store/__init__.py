"""状态中心：设置和运行状态的唯一来源，任何变化都会通知订阅者（ARCHITECTURE「状态中心」）。

状态是一棵以点号路径寻址的树，例如 ``status.current.arrangement``。修改按路径进行，
订阅者收到 ``[(路径, 新值), ...]``。订阅回调在修改者的线程里执行，必须很快返回；
控制接口在回调里只把变化转交给自己的事件循环。
"""
from __future__ import annotations

import copy
import threading
from typing import Any, Callable

Change = tuple[str, Any]
Listener = Callable[[list[Change]], None]


class Store:
    def __init__(self, initial: dict | None = None):
        self._lock = threading.RLock()
        self._data: dict = copy.deepcopy(initial) if initial else {}
        self._listeners: list[Listener] = []

    def snapshot(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._data)

    def get(self, path: str, default: Any = None) -> Any:
        with self._lock:
            node: Any = self._data
            for key in path.split("."):
                if not isinstance(node, dict) or key not in node:
                    return default
                node = node[key]
            return copy.deepcopy(node)

    def set(self, path: str, value: Any) -> None:
        self.update({path: value})

    def update(self, changes: dict[str, Any]) -> None:
        """一次修改多个路径；只通知真正变化了的项。"""
        applied: list[Change] = []
        with self._lock:
            for path, value in changes.items():
                keys = path.split(".")
                node = self._data
                for key in keys[:-1]:
                    nxt = node.get(key)
                    if not isinstance(nxt, dict):
                        nxt = {}
                        node[key] = nxt
                    node = nxt
                if keys[-1] in node and node[keys[-1]] == value:
                    continue
                node[keys[-1]] = copy.deepcopy(value)
                applied.append((path, copy.deepcopy(value)))
            listeners = list(self._listeners)
        if applied:
            for fn in listeners:
                fn(applied)

    def subscribe(self, fn: Listener) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(fn)

        def unsubscribe() -> None:
            with self._lock:
                if fn in self._listeners:
                    self._listeners.remove(fn)

        return unsubscribe
