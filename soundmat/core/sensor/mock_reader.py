"""Mock 数据源：离线开发/测试用，无需 ESP32 与传感器。

两种用法：
- **回放**：从 `.npz`（key ``frames`` shape (N, RINGS, SLICES) + 可选 ``fps``）按帧率回放。
- **手动注入**：构造时不给 recording，用 `inject(cells, pressure)` 直接放/拿石头，
  立即 `_emit` 一帧。供 Web 虚拟垫面 / 单元测试驱动。
"""
from __future__ import annotations

import time
from collections.abc import Iterable

import numpy as np

from ... import config
from .reader import SensorReader

# 放下石头时该格的“按下”ADC 值。固件值越大压力越大（设计文档：压力越大电阻越低，
# Vout 随分压改变）；这里用一个明显高于空闲基线的值表示有物体。
# 须高于 SENSOR_THRESHOLD；真实/mock 共用「高值=有压力」约定
DEFAULT_PRESSURE = 600
IDLE_VALUE = 0


def empty_matrix() -> np.ndarray:
    return np.full((config.NUM_RINGS, config.NUM_SLICES), IDLE_VALUE, dtype=np.int16)


def matrix_from_cells(cells: Iterable[tuple[int, int]], pressure: int = DEFAULT_PRESSURE) -> np.ndarray:
    """由 (ring, slice) wire 集合生成压力矩阵（Mock 虚拟垫点击的是 S 坐标）。"""
    m = empty_matrix()
    for ring, slc in cells:
        if not (0 <= ring < config.NUM_RINGS and 0 <= slc < config.NUM_SLICES):
            continue
        m[ring, slc] = pressure
    return m


class MockSensorReader(SensorReader):
    def __init__(
        self,
        recording: str | None = None,
        *,
        fps: float = 30.0,
        loop: bool = True,
    ):
        super().__init__()
        self.fps = fps
        self.loop = loop
        self._frames: np.ndarray | None = None
        self._cells: set[tuple[int, int]] = set()
        if recording is not None:
            data = np.load(recording)
            self._frames = data["frames"].astype(np.int16)
            if "fps" in data:
                self.fps = float(data["fps"])

    # ── 手动注入（无 recording 时） ──
    def inject(self, cells: Iterable[tuple[int, int]], pressure: int = DEFAULT_PRESSURE) -> None:
        """设置当前“有石头”的格子并立即发一帧。"""
        self._cells = set(cells)
        self._emit(matrix_from_cells(self._cells, pressure))

    def place(self, ring: int, slc: int, pressure: int = DEFAULT_PRESSURE) -> None:
        self._cells.add((ring, slc))
        self._emit(matrix_from_cells(self._cells, pressure))

    def remove(self, ring: int, slc: int) -> None:
        self._cells.discard((ring, slc))
        self._emit(matrix_from_cells(self._cells))

    # ── 后台线程 ──
    def _run(self) -> None:
        if self._frames is None:
            # 手动注入模式：维持空闲帧心跳，等待 inject/place/remove
            while not self._stop.is_set():
                self._emit(matrix_from_cells(self._cells))
                time.sleep(1.0 / max(self.fps, 1.0))
            return

        period = 1.0 / max(self.fps, 1.0)
        i = 0
        n = len(self._frames)
        while not self._stop.is_set():
            self._emit(self._frames[i].copy())
            i += 1
            if i >= n:
                if not self.loop:
                    break
                i = 0
            time.sleep(period)
