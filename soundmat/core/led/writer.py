"""LEDWriter：维护最近一帧 LED buffer，按固定帧率编码成 L 帧通过串口发回 ESP32。

L 帧（固件设计文档）：``L:RRGGBB,RRGGBB,...,RRGGBB*XX\\n``，108 个 6 位十六进制 RGB，
按灯带物理编号排列。校验同 S 帧（TYPE..'*'前 的 XOR）。

模式每帧 `set_buffer(rgb_list)` 更新数据源；后台线程按 `fps`（默认 60Hz）取最近 buffer
发送，避免高频主循环灌爆串口。无串口时进入虚拟模式：只保留最近 buffer 供 Web 可视化。
"""
from __future__ import annotations

import threading
import time

from ... import config
from ..sensor.frame import compute_checksum

RGB = tuple[int, int, int]


def _clamp8(v: int) -> int:
    return 0 if v < 0 else 255 if v > 255 else int(v)


def encode_led_frame(buffer: list[RGB]) -> str:
    """108 个 (r,g,b) → 一行 L 帧（含 \\n）。不足/超出按 NUM_LEDS 截断或补黑。"""
    leds = list(buffer)[: config.NUM_LEDS]
    if len(leds) < config.NUM_LEDS:
        leds += [(0, 0, 0)] * (config.NUM_LEDS - len(leds))
    payload = ",".join(f"{_clamp8(r):02X}{_clamp8(g):02X}{_clamp8(b):02X}" for r, g, b in leds)
    body = f"{config.SERIAL_FRAME_LED}:{payload}"
    chk = compute_checksum(body.encode("ascii"))
    return f"{body}*{chk:02X}\n"


class LEDWriter:
    def __init__(self, fps: float = 60.0):
        self.fps = fps
        self._serial = None
        self._buffer: list[RGB] = [(0, 0, 0)] * config.NUM_LEDS
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def attach_serial(self, serial_obj) -> None:
        """复用已打开的 pyserial 句柄（与传感器共用一条串口）。"""
        self._serial = serial_obj

    # ── 数据源 ──
    def set_buffer(self, buffer: list[RGB]) -> None:
        with self._lock:
            self._buffer = list(buffer)

    def clear(self) -> None:
        self.set_buffer([(0, 0, 0)] * config.NUM_LEDS)

    def latest(self) -> list[RGB]:
        with self._lock:
            return list(self._buffer)

    # ── 生命周期 ──
    def start(self) -> "LEDWriter":
        if self._thread is not None:
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="led-writer")
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self) -> None:
        period = 1.0 / max(self.fps, 1.0)
        while not self._stop.is_set():
            if self._serial is not None:
                frame = encode_led_frame(self.latest())
                try:
                    self._serial.write(frame.encode("ascii"))
                except Exception as e:
                    print(f"[led] serial write error: {e}")
            time.sleep(period)
