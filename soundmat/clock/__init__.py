"""时钟：统一的时间基准和声音化的固定节拍（DATA_MODEL「节拍与时间窗」）。

所有运行时数据使用同一个单调递增的系统时间（秒）。时钟按固定节拍驱动声音化，
每一拍给出节拍序号和当前系统时间；前瞻时间窗的长度（提前量）由模式决定。
需要音乐时间的模式自己维护从系统时间到音乐时间的换算。
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable

from ..rates import RateMeter

log = logging.getLogger("soundmat.clock")


def system_time() -> float:
    """系统时间：单调递增，单位秒。"""
    return time.monotonic()


@dataclass(frozen=True)
class Beat:
    index: int
    t: float                 # 这一拍的系统时间
    period: float            # 节拍间隔

    def window(self, lookahead: float) -> tuple[float, float]:
        """前瞻时间窗：从当前时刻到当前时刻加上提前量。"""
        return self.t, self.t + lookahead


class BeatClock:
    """在独立线程里按固定频率调用回调。回调超时不会让节拍堆积：落后时跳到当前时刻。"""

    def __init__(self, hz: float, on_beat: Callable[[Beat], None], name: str = "beat"):
        self.period = 1.0 / hz
        self._on_beat = on_beat
        self._name = name
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.overruns = 0                  # 计算超过一个节拍间隔的次数
        self.rate = RateMeter()            # 实际节拍率
        self.index = 0

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        next_t = system_time()
        while not self._stop.is_set():
            now = system_time()
            self.rate.tick(now)
            try:
                self._on_beat(Beat(self.index, now, self.period))
            except Exception:  # 节拍线程不能因为一次异常停下
                log.exception("节拍回调出错")
            self.index += 1
            next_t += self.period
            delay = next_t - system_time()
            if delay > 0:
                self._stop.wait(delay)
            else:
                self.overruns += 1
                next_t = system_time()
