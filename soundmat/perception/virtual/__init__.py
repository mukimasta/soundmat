"""虚拟垫子：开发时在浏览器里点一个区就是放一颗石头，再点一次拿起（DECISION 第 2 条）。

它产生压力图，从垫面信号的出口接入；之后的垫面解读、声音化和声音引擎与真机完全一样。
为了让去抖照常工作，它像控制器一样按固定帧率持续产生压力图，而不是只在点击时产生一次。
"""
from __future__ import annotations

import threading
from typing import Callable

import numpy as np

from ...clock import system_time
from ..model import PressureMap
from ..zones import NUM_ZONES

# 虚拟石头的归一化压力（约等于 ADC 读数 2048），高于占用阈值
STONE_PRESSURE = 0.5


class VirtualMat:
    def __init__(self, on_pressure: Callable[[PressureMap], None], frame_hz: float = 60.0):
        self._on_pressure = on_pressure
        self._period = 1.0 / frame_hz
        self._lock = threading.Lock()
        self._stones: set[int] = set()
        self._seq = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def stones(self) -> frozenset[int]:
        with self._lock:
            return frozenset(self._stones)

    def toggle(self, zone: int) -> bool:
        """切换一个区；返回切换后这个区是否有石头。"""
        if not 0 <= zone < NUM_ZONES:
            raise ValueError(f"区域序号超出范围：{zone}")
        with self._lock:
            if zone in self._stones:
                self._stones.discard(zone)
                return False
            self._stones.add(zone)
            return True

    def set(self, zone: int, present: bool) -> None:
        if not 0 <= zone < NUM_ZONES:
            raise ValueError(f"区域序号超出范围：{zone}")
        with self._lock:
            (self._stones.add if present else self._stones.discard)(zone)

    def clear(self) -> None:
        with self._lock:
            self._stones.clear()

    def frame(self, t: float | None = None) -> PressureMap:
        """按当前石头产生一张压力图。"""
        values = np.zeros(NUM_ZONES, dtype=np.float32)
        with self._lock:
            if self._stones:
                values[list(self._stones)] = STONE_PRESSURE
            self._seq += 1
            seq = self._seq
        return PressureMap(t=system_time() if t is None else t, seq=seq, values=values)

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="virtual-mat", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        next_t = system_time()
        while not self._stop.is_set():
            self._on_pressure(self.frame())
            next_t += self._period
            delay = next_t - system_time()
            if delay > 0:
                self._stop.wait(delay)
            else:
                next_t = system_time()
