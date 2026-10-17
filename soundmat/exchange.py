"""线程之间交换数据的两种容器（TECH_STACK「主机程序」、DATA_MODEL「数据流向」）。

- ``Latest``：最新值。产生者覆盖，使用者读取当前这一份，两边不互相等待。
- ``EventQueue``：不能丢失的离散事件。使用者每次取走自上次以来积累的全部事件。
  ``EventHub`` 把同一串事件分发给多个使用者，每个使用者有自己的队列。
"""
from __future__ import annotations

import threading
from collections import deque
from typing import Generic, TypeVar

T = TypeVar("T")


class Latest(Generic[T]):
    def __init__(self, initial: T | None = None):
        self._lock = threading.Lock()
        self._value = initial
        self._version = 0

    def set(self, value: T) -> None:
        with self._lock:
            self._value = value
            self._version += 1

    def get(self) -> T | None:
        with self._lock:
            return self._value

    def get_versioned(self) -> tuple[T | None, int]:
        """返回值和版本号；版本号每次 set 加一，用来判断是否有新值。"""
        with self._lock:
            return self._value, self._version


class EventQueue(Generic[T]):
    def __init__(self, maxlen: int = 10000):
        self._lock = threading.Lock()
        self._items: deque[T] = deque(maxlen=maxlen)

    def put(self, item: T) -> None:
        with self._lock:
            self._items.append(item)

    def put_many(self, items) -> None:
        with self._lock:
            self._items.extend(items)

    def drain(self) -> list[T]:
        with self._lock:
            out = list(self._items)
            self._items.clear()
            return out

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


class EventHub(Generic[T]):
    """一个事件源、多个使用者：每个使用者订阅后得到自己的队列，互不影响。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._queues: list[EventQueue[T]] = []

    def subscribe(self) -> EventQueue[T]:
        q: EventQueue[T] = EventQueue()
        with self._lock:
            self._queues.append(q)
        return q

    def unsubscribe(self, q: EventQueue[T]) -> None:
        with self._lock:
            if q in self._queues:
                self._queues.remove(q)

    def publish(self, items: list[T]) -> None:
        if not items:
            return
        with self._lock:
            queues = list(self._queues)
        for q in queues:
            q.put_many(items)
