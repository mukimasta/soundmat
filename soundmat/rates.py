"""实测速率：统计最近 1 秒内发生了多少次，用来在看板上对照各条链路的期望帧率。

产生者在每次发生时调用 ``tick``，读取的一方随时调用 ``rate``；两边可以在不同线程。
"""
from __future__ import annotations

import threading
from collections import deque

from .timebase import system_time

WINDOW = 1.0  # 秒


class RateMeter:
    def __init__(self, maxlen: int = 512):
        self._lock = threading.Lock()
        self._times: deque[float] = deque(maxlen=maxlen)

    def tick(self, now: float | None = None) -> None:
        with self._lock:
            self._times.append(system_time() if now is None else now)

    def rate(self, now: float | None = None) -> float:
        """最近 1 秒的次数（次/秒）。"""
        now = system_time() if now is None else now
        with self._lock:
            return float(sum(1 for t in self._times if now - t <= WINDOW))
