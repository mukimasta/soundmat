"""状态中心：设置和运行状态的唯一来源，任何变化都会通知订阅者（ARCHITECTURE「状态中心」）。

状态是一棵以点号路径寻址的树，例如 ``status.current.arrangement``。修改按路径进行，
订阅者收到 ``[(路径, 新值), ...]``。订阅回调在修改者的线程里执行，必须很快返回；
控制接口在回调里只把变化转交给自己的事件循环。

状态树分成若干段（``branches.BRANCHES``），每段只有一个写入者：模块用 ``writer(...)`` 领取
自己的段，得到只能写这些段的 ``Writer``。被领取的段不能再直接用 ``Store.update`` 写。
"""
from __future__ import annotations

import copy
import threading
from typing import Any, Callable

from .branches import BRANCHES, branch_of

Change = tuple[str, Any]
Listener = Callable[[list[Change]], None]


class Store:
    def __init__(self, initial: dict | None = None):
        self._lock = threading.RLock()
        self._data: dict = copy.deepcopy(initial) if initial else {}
        self._listeners: list[Listener] = []
        self._owned: dict[str, "Writer"] = {}

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
        """一次修改多个路径（只能是没有被领取的段）；只通知真正变化了的项。"""
        self._apply(changes, None)

    def writer(self, *branches: str) -> "Writer":
        """领取状态树的若干段，返回只能写这些段的写入口。每段只能被领取一次。"""
        w = Writer(self, frozenset(branches))
        with self._lock:
            for b in branches:
                if b not in BRANCHES:
                    raise KeyError(f"状态树没有登记这一段：{b}（见 store/branches.py）")
                if b in self._owned:
                    raise RuntimeError(f"状态树的 {b} 已经有写入者")
            for b in branches:
                self._owned[b] = w
        return w

    def _apply(self, changes: dict[str, Any], writer: "Writer | None") -> None:
        for path in changes:
            b = branch_of(path)
            if writer is not None:
                allowed = b in writer.branches
            else:
                allowed = b not in self._owned and not any(o.startswith(path + ".") for o in self._owned)
            if not allowed:
                raise PermissionError(f"{path} 不属于这个写入者（见 store/branches.py）")
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


class Writer:
    """状态树若干段的写入口（``Store.writer``）。读取不受限制。"""

    def __init__(self, store: Store, branches: frozenset[str]):
        self.store = store
        self.branches = branches

    def set(self, path: str, value: Any) -> None:
        self.store._apply({path: value}, self)

    def update(self, changes: dict[str, Any]) -> None:
        self.store._apply(changes, self)

    def get(self, path: str, default: Any = None) -> Any:
        return self.store.get(path, default)
