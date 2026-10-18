"""灯光引擎：按固定刷新率把灯光意图变成灯光帧（ARCHITECTURE「灯光引擎、设备连接与运行管理」）。

每一帧取当前的灯光意图，再叠上系统提示层（例如录制倒计时，优先级最高），从低到高按不透明度
合成到黑底上，得到逻辑顺序的颜色；施加灯带的物理对齐偏移后交给设备连接。刷新率由它统一决定，
与声音化每秒算几次无关；不过声音化交出新的灯光意图时会立刻合成一帧，两个时钟错开时也不会
漏掉或重复一份意图，没有新意图时（例如只有录制倒计时在变）按自己的刷新率继续。合成结果（物理偏移之前）也作为控制台的灯环预览：与灯光引擎同频，
颜色没有变化的帧不更新预览；预览编码成十六进制字符串（每颗灯 6 个字符 rrggbb，逻辑顺序）。
"""
from __future__ import annotations

import threading
from typing import Callable

import numpy as np

from ..timebase import system_time
from ..config import LightConfig
from ..exchange import Latest
from ..rates import RateMeter
from ..intent import LightIntent, LightLayer


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


def to_hex(colors: np.ndarray) -> str:
    """(N, 3) 的 0–255 颜色 → 十六进制字符串，每颗灯 6 个字符 rrggbb。"""
    return np.ascontiguousarray(colors, dtype=np.uint8).tobytes().hex()


class LightEngine:
    def __init__(self, cfg: LightConfig, intent: Latest[LightIntent],
                 send: Callable[[np.ndarray], bool] | None = None):
        self.cfg = cfg
        self.intent = intent
        self.send = send
        self.system: dict[str, LightLayer] = {}
        self._lock = threading.Lock()
        self.preview: Latest[dict] = Latest()
        self._last_preview: str | None = None
        self._stop = threading.Event()
        self._fresh = threading.Event()  # 声音化交出了新的灯光意图
        self._unsub = None
        self._thread: threading.Thread | None = None
        self.frames = 0
        self.rate = RateMeter()          # 灯光引擎实际合成的帧率
        self.sent = RateMeter()          # 实际写给控制器的帧率（控制器没就绪时不算）

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
        if self.send is not None and self.send(to_physical(colors, self.cfg.led_offset)):
            self.sent.tick(now)
        hex_colors = to_hex(colors)
        if hex_colors != self._last_preview:
            self._last_preview = hex_colors
            self.preview.set({"colors": hex_colors})
        self.frames += 1
        self.rate.tick(now)
        return colors

    def rates(self) -> dict[str, dict]:
        """给系统监测：合成的帧率，以及写给控制器的帧率（没有控制器时为 None）。"""
        hz = self.cfg.refresh_hz
        wired = self.send is not None
        return {"light": {"actual": self.rate.rate(), "expected": hz},
                "ledWrites": {"actual": self.sent.rate() if wired else None, "expected": hz if wired else None}}

    def start(self) -> None:
        self._stop.clear()
        self._unsub = self.intent.subscribe(self._fresh.set)
        self._thread = threading.Thread(target=self._run, name="light", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._fresh.set()
        if self._unsub:
            self._unsub()
            self._unsub = None
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        """有新意图就合成；没有新意图时最迟每个刷新周期合成一次。

        刷新率同时是上限：两帧之间至少间隔周期的 75%（留出意图到达时间的抖动，否则 60 Hz 时会漏帧）。刷新率与声音化相同（60）时每份新意图都会合成；
        设得更低（例如 Pi 3B 上的 30）时，多出来的意图只保留最新的一份。
        """
        period = 1.0 / self.cfg.refresh_hz
        last = 0.0
        while not self._stop.is_set():
            self._fresh.wait(period)
            if self._stop.is_set():
                break
            gap = system_time() - last
            if gap < period * 0.75:
                self._stop.wait(period * 0.75 - gap)
            self._fresh.clear()
            last = system_time()
            self.render(last)
