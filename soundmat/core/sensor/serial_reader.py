"""真实数据源：从 ESP32 USB 串口读 S 帧。

固件每完成一轮扫描立即发一行 ``S:...*XX\\n``。我们按行读取（严格按 \\n 分帧，
半帧留待下次拼接），校验失败的帧直接丢弃（环境/Lo-Fi 音乐场景丢一帧无感知）。
"""
from __future__ import annotations

import numpy as np

from ... import config
from .frame import FrameError, parse_sensor_frame, values_to_matrix
from .reader import SensorReader


class SerialSensorReader(SensorReader):
    def __init__(self, port: str | None = None, baud: int | None = None, *, verify: bool = True):
        super().__init__()
        self.port = port or config.SERIAL_PORT
        self.baud = baud or config.SERIAL_BAUD
        self.verify = verify
        self._serial = None  # 复用给 LEDWriter 时可外部注入

    def attach_serial(self, serial_obj) -> None:
        """复用已打开的 pyserial 句柄（与 LEDWriter 共用一条串口）。"""
        self._serial = serial_obj

    def _open(self):
        import serial  # 延迟导入，离线/无 pyserial 时不影响 mock 路径

        return serial.Serial(self.port, self.baud, timeout=1.0)

    def _run(self) -> None:
        ser = self._serial or self._open()
        buf = b""
        bad = 0
        while not self._stop.is_set():
            chunk = ser.read(512)
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
                self._emit(values_to_matrix(values.astype(np.int16)))
