"""真实数据源：从 ESP32 USB 串口读 S 帧。

固件每完成一轮扫描立即发一行 ``S:...*XX\\n``。我们按行读取（严格按 \\n 分帧，
半帧留待下次拼接），校验失败的帧直接丢弃（环境/Lo-Fi 音乐场景丢一帧无感知）。
"""
from __future__ import annotations

import numpy as np
from collections.abc import Callable

from ... import config
from .frame import FrameError, parse_sensor_frame, values_to_matrix
from .reader import SensorReader


class SerialSensorReader(SensorReader):
    def __init__(
        self,
        port: str | None = None,
        baud: int | None = None,
        *,
        verify: bool = True,
        on_serial_lost: Callable[[], None] | None = None,
    ):
        super().__init__()
        self.port = port or config.SERIAL_PORT
        self.baud = baud or config.SERIAL_BAUD
        self.verify = verify
        self._on_serial_lost = on_serial_lost
        self._serial_lost = False
        self._serial = None  # 复用给 LEDWriter 时可外部注入

    def attach_serial(self, serial_obj) -> None:
        """复用已打开的 pyserial 句柄（与 LEDWriter 共用一条串口）。"""
        self._serial = serial_obj

    def _notify_serial_lost(self, err: Exception) -> None:
        if self._serial_lost:
            return
        self._serial_lost = True
        self._serial = None
        print(f"[sensor] 串口不可用: {err}")
        if self._on_serial_lost is not None:
            try:
                self._on_serial_lost()
            except Exception:
                pass

    def _open(self):
        from ..esp32_serial import open_esp32_serial, pick_serial_port

        port = pick_serial_port(self.port)
        return open_esp32_serial(port, self.baud)

    def _run(self) -> None:
        ser = self._serial or self._open()
        buf = b""
        bad = 0
        while not self._stop.is_set():
            try:
                chunk = ser.read(512)
            except OSError as e:
                self._notify_serial_lost(e)
                return
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.decode("ascii", errors="replace").strip()
                if not text or text.startswith(config.SERIAL_FRAME_DEBUG):
                    if text.startswith(config.SERIAL_FRAME_DEBUG):
                        print(f"[esp32] {text}")
                    continue
                if not text.startswith(config.SERIAL_FRAME_SENSOR + ":"):
                    continue
                try:
                    values = parse_sensor_frame(text, verify=self.verify)
                except FrameError:
                    bad += 1
                    continue
                matrix = values_to_matrix(values.astype(np.int16))
                self._emit(matrix)
