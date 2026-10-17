"""灯光引擎：按固定刷新率把灯光意图变成灯光帧（ARCHITECTURE「灯光引擎、设备连接与运行管理」）。

每一帧取当前的灯光意图，再叠上系统提示层（例如录制倒计时，优先级最高），从低到高按不透明度
合成到黑底上，得到逻辑顺序的颜色；施加灯带的物理对齐偏移后交给设备连接。刷新率由它统一决定，
与声音化每秒算几次无关。合成结果（物理偏移之前）也作为控制台的灯环预览。
"""
from __future__ import annotations

import threading
from typing import Callable

import numpy as np

from ..clock import system_time
from ..config import LightConfig
from ..exchange import Latest
from ..sonification.intent import LightIntent, LightLayer

PREVIEW_HZ = 30.0


def composite(layers, led_count: int) -> np.ndarray:
    """按优先级从低到高合成到黑底上，返回 (N, 3) 的 0–255 颜色。"""
    out = np.zeros((led_count, 3), dtype=np.float32)
    for layer in sorted(layers, key=lambda l: l.priority):
        if layer.rgb.shape != (led_count, 3):
            continue
        a = np.clip(layer.alpha, 0, 1)[:, None]
        out = out * (1 - a) + np.clip(layer.rgb, 0, 1) * a
    return np.round(out * 255).astype(np.uint8)


def to_physical(colors: np.ndarray, offset: int) -> np.ndarray:
    """逻辑位置 k 的颜色写到物理灯珠 (k + offset) mod N。"""
    return np.roll(colors, offset % len(colors), axis=0)


class LightEngine:
    def __init__(self, cfg: LightConfig, intent: Latest[LightIntent],
                 send: Callable[[np.ndarray], None] | None = None):
        self.cfg = cfg
        self.intent = intent
        self.send = send
        self.system: dict[str, LightLayer] = {}
        self._lock = threading.Lock()
        self.preview: Latest[dict] = Latest()
        self._next_preview = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.frames = 0

    def set_system_layer(self, name: str, layer: LightLayer | None) -> None:
        """设置或移除一个系统提示层（例如录制倒计时），它叠在声音化的灯光之上。"""
        with self._lock:
            if layer is None:
                self.system.pop(name, None)
            else:
                self.system[name] = layer

    def render(self, now: float) -> np.ndarray:
        intent = self.intent.get() or LightIntent()
        with self._lock:
            system = list(self.system.values())
        colors = composite(list(intent.layers) + system, self.cfg.led_count)
        if self.send is not None:
            self.send(to_physical(colors, self.cfg.led_offset))
        if now >= self._next_preview:
            self._next_preview = now + 1.0 / PREVIEW_HZ
            self.preview.set({"colors": [None if not c.any() else [int(x) for x in c] for c in colors]})
        self.frames += 1
        return colors

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="light", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        period = 1.0 / self.cfg.refresh_hz
        next_t = system_time()
        while not self._stop.is_set():
            self.render(system_time())
            next_t += period
            delay = next_t - system_time()
            if delay > 0:
                self._stop.wait(delay)
            else:
                next_t = system_time()
