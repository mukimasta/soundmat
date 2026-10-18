"""按固定间隔在独立线程里做一件事，例如采样电平、系统监测。"""
from __future__ import annotations

import logging
import threading
from typing import Callable

from .timebase import system_time

log = logging.getLogger("soundmat")


class Periodic:
    """每隔 ``period`` 秒调用一次 ``fn(now)``，启动时先调用一次。出错只记日志，不会停下。"""

    def __init__(self, name: str, period: float, fn: Callable[[float], object]):
        self.name = name
        self.period = period
        self.fn = fn
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=self.name, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.fn(system_time())
            except Exception:
                log.exception("%s 出错", self.name)
            self._stop.wait(self.period)
