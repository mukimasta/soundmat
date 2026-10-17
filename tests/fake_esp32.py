"""模拟控制器：像 ESP32 一样发 S 帧，记录收到的 L 帧。"""
from __future__ import annotations

import threading
import time

import numpy as np

from soundmat.device.protocol import encode_sensor_frame


class FakeESP32:
    def __init__(self, boot_lines: int = 2, hz: float = 200.0):
        self.values = np.zeros(256, dtype=np.int16)
        self.received: list[bytes] = []
        self.boot_lines = boot_lines      # 开机期间只发调试行
        self.period = 1.0 / hz
        self.closed = False
        self.fail_after: int | None = None
        self.corrupt_next = 0
        self.sent = 0
        self._lock = threading.Lock()
        self._buf = b""

    def read(self, size: int) -> bytes:
        if self.closed:
            raise OSError("closed")
        time.sleep(self.period)
        if self.fail_after is not None and self.sent >= self.fail_after:
            raise OSError("device unplugged")
        if self.boot_lines > 0:
            self.boot_lines -= 1
            return b"# booting\n"
        with self._lock:
            line = encode_sensor_frame(self.values).encode()
        if self.corrupt_next:
            self.corrupt_next -= 1
            line = line.replace(b"*", b"0*", 1)
        self.sent += 1
        return line

    def write(self, data: bytes) -> int:
        self.received.append(data)
        return len(data)

    def close(self) -> None:
        self.closed = True

    def press(self, wire_index: int, value: int) -> None:
        with self._lock:
            self.values[wire_index] = value
