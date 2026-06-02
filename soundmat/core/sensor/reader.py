"""SensorReader 抽象接口 + 帧数据类型。

模式 app 只跟 `SensorReader` 接口打交道，不知道数据来自真实串口还是 mock 回放——
换一行构造代码就能切换数据源。

reader 在后台线程持续读帧，维护「最近一帧」供主循环按需 `latest()` 拉取；也支持
`subscribe()` 回调（Web 流、录制用）。读取与消费解耦：串口阻塞读独立线程，主循环不阻塞。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from ... import config
from .normalize import normalize_wire_matrix


@dataclass(frozen=True)
class SensorFrame:
    """一帧传感快照。matrix[ring][slice] = 原始 ADC 值（-1 无效）。"""

    matrix: np.ndarray            # shape (NUM_RINGS, NUM_SLICES), int16；已做 slice 镜像（若启用）
    timestamp: float              # time.monotonic() 接收时刻
    seq: int = 0                  # 帧序号（自增）

    @property
    def values(self) -> np.ndarray:
        return self.matrix.reshape(-1)


Callback = Callable[[SensorFrame], None]


class SensorReader:
    """传感数据源抽象基类。子类实现 `_run()` 循环往 `_emit()` 推帧。"""

    def __init__(self) -> None:
        self._latest: SensorFrame | None = None
        self._lock = threading.Lock()
        self._subscribers: list[Callback] = []
        self._sub_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._seq = 0

    # ── 生命周期 ──
    def start(self) -> "SensorReader":
        if self._thread is not None:
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_guarded, daemon=True, name="sensor-reader")
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    # ── 消费端 ──
    def latest(self) -> SensorFrame | None:
        with self._lock:
            return self._latest

    def subscribe(self, callback: Callback) -> Callable[[], None]:
        """注册帧回调，返回取消订阅的函数。"""
        with self._sub_lock:
            self._subscribers.append(callback)

        def unsubscribe() -> None:
            with self._sub_lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)

        return unsubscribe

    # ── 子类用 ──
    def _emit(self, matrix: np.ndarray) -> None:
        matrix = normalize_wire_matrix(matrix)
        frame = SensorFrame(matrix=matrix, timestamp=time.monotonic(), seq=self._seq)
        self._seq += 1
        with self._lock:
            self._latest = frame
        with self._sub_lock:
            subs = list(self._subscribers)
        for cb in subs:
            try:
                cb(frame)
            except Exception as e:  # 一个订阅者出错不影响其他人
                print(f"[sensor] subscriber error: {e}")

    def _run_guarded(self) -> None:
        try:
            self._run()
        except Exception as e:
            print(f"[sensor] reader thread crashed: {e}")

    def _run(self) -> None:  # pragma: no cover - 抽象
        raise NotImplementedError
