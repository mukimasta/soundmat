"""时钟：声音化的固定节拍（DATA_MODEL「节拍与时间窗」）。

时间基准是 ``timebase.system_time``。时钟按固定节拍驱动声音化，
每一拍给出节拍序号和当前系统时间；前瞻时间窗的长度（提前量）由模式决定。
需要音乐时间的模式自己维护从系统时间到音乐时间的换算。
"""
from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass
from typing import Callable

from ..rates import RateMeter
from ..timebase import system_time

log = logging.getLogger("soundmat.clock")


@dataclass(frozen=True)
class Beat:
    index: int
    t: float                 # 这一拍的系统时间
    period: float            # 节拍间隔

    def window(self, lookahead: float) -> tuple[float, float]:
        """前瞻时间窗：从当前时刻到当前时刻加上提前量。"""
        return self.t, self.t + lookahead


LAG_WINDOW = 60.0  # 秒：最近多长时间内的最大节拍延迟


class BeatClock:
    """在独立线程里按固定频率调用回调。回调超时不会让节拍堆积：落后时跳到当前时刻。

    除了实际节拍率，还记录每一拍比计划晚开始了多久（节拍延迟）。几毫秒的延迟无害：声音都带时间戳、
    有前瞻和输出延迟兜着；只有延迟超过 ``stall_after`` 秒（配置的迟到容忍度）才可能让定时声音迟到，
    这样的一拍计为一次「卡住」。
    """

    def __init__(self, hz: float, on_beat: Callable[[Beat], None], name: str = "beat",
                 stall_after: float = 0.05):
        self.period = 1.0 / hz
        self.stall_after = stall_after
        self._on_beat = on_beat
        self._name = name
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.stalls = 0                    # 节拍延迟超过 stall_after 的次数
        self._lags: deque[tuple[float, float]] = deque()   # (时刻, 延迟)，只记超过一个节拍间隔的
        self._lock = threading.Lock()
        self.rate = RateMeter()            # 实际节拍率
        self.index = 0

    def max_lag(self, now: float | None = None) -> float:
        """最近 1 分钟里最大的节拍延迟（秒）；都在一个节拍间隔以内时为 0。"""
        now = system_time() if now is None else now
        with self._lock:
            while self._lags and now - self._lags[0][0] > LAG_WINDOW:
                self._lags.popleft()
            return max((lag for _, lag in self._lags), default=0.0)

    def _note_lag(self, now: float, lag: float) -> None:
        if lag > self.period:
            with self._lock:
                self._lags.append((now, lag))
        if lag > self.stall_after:
            self.stalls += 1

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
            self._note_lag(now, now - next_t)
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
                # 落后了：先记下比计划晚了多少（这一拍算得太久时，延迟就在这里体现），再跳到当前时刻
                now = system_time()
                self._note_lag(now, now - next_t)
                next_t = now
