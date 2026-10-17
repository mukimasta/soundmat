"""串口选择（沿用第一版 ``core/esp32_serial.py`` 的规则）。

- Mac：只看 ``/dev/cu.*``（call-out 设备，避免 tty 占口）。
- Linux / 树莓派：``ttyUSB*``、``ttyACM*``、``/dev/serial/by-id/*``；排除板载 UART（``ttyS*``、``ttyAMA*``、
  ``serial0/1``），它们不是 USB 上的 ESP32。
- 蓝牙等明显不是控制器的口被排除；其余按关键词打分取最高。
"""
from __future__ import annotations

import glob
import re
import sys

_BLOCKED = ("bluetooth", "debug-console", "airpod", "boseqc", "headset")
_ONBOARD_RE = re.compile(r"^/dev/tty(?:AMA|S)\d+$", re.IGNORECASE)
_ONBOARD_LINKS = frozenset({"/dev/serial0", "/dev/serial1"})
_KEYWORDS = (
    ("usbserial", 100), ("usbmodem", 100), ("ttyusb", 100), ("ttyacm", 100),
    ("tty.usb", 90), ("by-id", 85), ("slab", 80), ("wchusb", 80), ("ch340", 80),
    ("ch34", 70), ("cp210", 80), ("ftdi", 70), ("serial", 50),
)


def is_onboard_uart(path: str, platform: str = sys.platform) -> bool:
    if platform != "linux":
        return False
    low = path.lower()
    return low in _ONBOARD_LINKS or bool(_ONBOARD_RE.match(low))


def score(path: str) -> int:
    low = path.lower()
    return sum(pts for kw, pts in _KEYWORDS if kw in low)


def candidates(platform: str = sys.platform) -> list[str]:
    if platform == "darwin":
        paths = glob.glob("/dev/cu.*")
    else:
        paths = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*") + glob.glob("/dev/serial/by-id/*")
    try:
        from serial.tools import list_ports
        paths += [p.device for p in list_ports.comports()]
    except Exception:
        pass
    return filter_ports(paths, platform)


def filter_ports(paths, platform: str = sys.platform) -> list[str]:
    ok = {p for p in paths if not any(b in p.lower() for b in _BLOCKED) and not is_onboard_uart(p, platform)}
    if platform == "darwin":
        ok = {p for p in ok if p.startswith("/dev/cu.")}
    return sorted(ok, key=lambda p: (-score(p), p))


def pick_port(setting: str = "auto") -> str | None:
    """``auto`` 时返回得分最高的口（没有则 None），否则原样返回。"""
    if setting != "auto":
        return setting
    ports = candidates()
    return ports[0] if ports else None
