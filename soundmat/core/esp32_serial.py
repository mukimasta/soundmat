"""ESP32 USB 串口：自动选口、打开、等待固件就绪。

逻辑对齐 ``soundmat_firmware/tools``（plot_sensors / led_gui / led_test）：
- Mac：优先 ``/dev/cu.*``（call-out，避免 tty 占口）
- Linux / 树莓派：``ttyUSB*`` / ``ttyACM*`` / ``by-id``
- 打开时 ``dtr=rts=False``，避免 CH340 复位 ESP32
- 发 L 帧前等待首帧 ``S:``，避免 boot 窗口丢包
"""
from __future__ import annotations

import glob
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import serial

from .. import config

_BLOCKED = ("bluetooth", "debug-console", "airpod", "boseqc", "headset")

_PORT_KEYWORDS: tuple[tuple[str, int], ...] = (
    ("usbserial", 100),
    ("usbmodem", 100),
    ("ttyusb", 100),
    ("ttyacm", 100),
    ("tty.usb", 90),
    ("by-id", 85),
    ("slab", 80),
    ("wchusb", 80),
    ("ch340", 80),
    ("ch34", 70),
    ("cp210", 80),
    ("ftdi", 70),
    ("serial", 50),
)


def _port_score(path: str) -> tuple[int, str]:
    low = path.lower()
    score = 0
    for kw, pts in _PORT_KEYWORDS:
        if kw in low:
            score += pts
    return (-score, path)


def _glob_candidates() -> list[str]:
    if sys.platform == "darwin":
        return sorted(glob.glob("/dev/cu.*"))
    paths: list[str] = []
    paths.extend(glob.glob("/dev/ttyUSB*"))
    paths.extend(glob.glob("/dev/ttyACM*"))
    paths.extend(glob.glob("/dev/serial/by-id/*"))
    return sorted(set(paths))


def list_serial_ports() -> list[str]:
    """可用串口列表（已过滤蓝牙等）。"""
    try:
        from serial.tools import list_ports
    except ImportError:
        from_comports: list[str] = []
    else:
        from_comports = [p.device for p in list_ports.comports()]
    merged = sorted(set(from_comports + _glob_candidates()))
    return [p for p in merged if not any(b in p.lower() for b in _BLOCKED)]


def pick_serial_port(arg: str) -> str:
    """``auto`` 时按关键词打分选最佳口，否则返回给定路径。"""
    if arg != "auto":
        return arg
    ports = list_serial_ports()
    if not ports:
        raise RuntimeError(
            "未找到可用串口（auto）。请连接 ESP32 后重试，或用 --port / --list-ports"
        )
    ports.sort(key=_port_score)
    chosen = ports[0]
    print(f"[serial] auto: 选用 {chosen}", file=sys.stderr)
    if len(ports) > 1:
        extra = ports[1:6]
        suffix = "…" if len(ports) > 6 else ""
        print(f"[serial] auto: 其它候选 {extra}{suffix}", file=sys.stderr)
    return chosen


def print_serial_ports() -> None:
    try:
        from serial.tools import list_ports

        ports = list_ports.comports()
    except ImportError:
        ports = []
    if ports:
        print("pyserial 枚举:", file=sys.stderr)
        for p in ports:
            print(f"  {p.device}\t{p.description}", file=sys.stderr)
    usable = list_serial_ports()
    print("可用（过滤后）:", file=sys.stderr)
    if not usable:
        print("  （无）", file=sys.stderr)
        return
    for p in usable:
        print(f"  {p}", file=sys.stderr)


def open_esp32_serial(port: str, baud: int | None = None) -> serial.Serial:
    """打开串口，不触发 DTR/RTS 复位（与 firmware tools 一致）。"""
    import serial

    rate = config.SERIAL_BAUD if baud is None else baud
    ser = serial.Serial()
    ser.port = port
    ser.baudrate = rate
    ser.timeout = 0.25
    ser.write_timeout = 1.0
    ser.dtr = False
    ser.rts = False
    ser.open()
    time.sleep(0.15)
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    return ser


def wait_for_esp32_boot(ser: serial.Serial, timeout: float = 8.0) -> bool:
    """阻塞直到收到一行 ``S:`` 帧，或超时。

    macOS/CH340 打开串口可能复位芯片；须等 app_main 跑到 921600 并发 S 帧后再发 L。
    """
    deadline = time.monotonic() + timeout
    buf = bytearray()
    while time.monotonic() < deadline:
        chunk = ser.read(4096)
        if chunk:
            buf.extend(chunk)
        while b"\n" in buf:
            raw, _, buf = buf.partition(b"\n")
            line = raw.rstrip(b"\r").decode("ascii", errors="ignore")
            if line.startswith("#"):
                print(f"[esp32] {line}")
            elif line.startswith("S:"):
                return True
    return False
