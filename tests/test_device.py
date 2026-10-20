import threading
import time

import numpy as np
import pytest

from soundmat.device import DeviceLink, _ReadArrived
from soundmat.device.ports import filter_ports
from soundmat.device.protocol import FrameError, checksum, encode_led_frame, encode_sensor_frame, parse_sensor_frame

from fake_esp32 import FakeESP32


def test_sensor_frame_roundtrip_and_errors():
    vals = np.arange(256) % 4096 - 1
    line = encode_sensor_frame(vals).strip()
    assert (parse_sensor_frame(line) == vals).all()
    with pytest.raises(FrameError, match="校验"):
        parse_sensor_frame(line.replace("S:-1", "S:-2"))
    with pytest.raises(FrameError):
        parse_sensor_frame("S:1,2,3*" + f"{checksum(b'S:1,2,3'):02X}")
    with pytest.raises(FrameError):
        parse_sensor_frame("L:000000*00")


def test_led_frame_format():
    c = np.zeros((108, 3), dtype=np.uint8)
    c[0] = (255, 16, 1)
    frame = encode_led_frame(c).decode()
    assert frame.startswith("L:FF1001,000000,") and frame.endswith("\n")
    body, chk = frame.strip().rsplit("*", 1)
    assert int(chk, 16) == checksum(body.encode()) and body.count(",") == 107


def test_port_filtering_rules():
    linux = ["/dev/ttyS0", "/dev/ttyAMA0", "/dev/serial0", "/dev/ttyUSB0", "/dev/ttyACM0",
             "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"]
    assert filter_ports(linux, "linux")[0].startswith("/dev/serial/by-id/")   # 与第一版相同：by-id 名字得分最高
    assert not any("ttyS" in p or "AMA" in p or p == "/dev/serial0" for p in filter_ports(linux, "linux"))
    mac = ["/dev/tty.usbserial-10", "/dev/cu.usbserial-10", "/dev/cu.Bluetooth-Incoming-Port"]
    assert filter_ports(mac, "darwin") == ["/dev/cu.usbserial-10"]


def wait_for(cond, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_link_waits_for_boot_then_streams_and_sends_leds():
    esp = FakeESP32()
    frames, events = [], []
    link = DeviceLink(frames.append, opener=lambda p: esp, picker=lambda s: "/dev/fake",
                      on_event=lambda lvl, txt: events.append((lvl, txt)))
    leds = np.zeros((108, 3), dtype=np.uint8)
    link.send_leds(leds)                  # 还没连接：丢弃
    link.start()
    try:
        assert wait_for(lambda: len(frames) >= 5)
        assert ("info", "控制器已连接（/dev/fake）") in events
        link.send_leds(leds)
        link.send_leds(leds)
        assert len(esp.received) == 3     # 第一帧发两次
        esp.corrupt_next = 3
        assert wait_for(lambda: link.checksum_errors == 3)
        st = link.status()
        assert st["connected"] and st["port"] == "/dev/fake" and st["fps"] > 0
    finally:
        link.stop()


class PySerialPort:
    """按 pyserial 的读法：``read(n)`` 要凑满 n 个字节，凑不满就等到超时；``in_waiting`` 是已经到了的字节数。
    控制器的字节由测试用 ``send`` 放进来。"""
    timeout = 0.1

    def __init__(self):
        self._cv = threading.Condition()
        self._buf = bytearray()
        self.closed = False

    @property
    def in_waiting(self) -> int:
        with self._cv:
            return len(self._buf)

    def send(self, data: bytes) -> None:
        with self._cv:
            self._buf += data
            self._cv.notify_all()

    def read(self, size: int) -> bytes:
        deadline = time.monotonic() + self.timeout
        with self._cv:
            while len(self._buf) < size and not self.closed:
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                self._cv.wait(left)
            out = bytes(self._buf[:size])
            del self._buf[:size]
            return out

    def write(self, data: bytes) -> int:
        return len(data)

    def close(self) -> None:
        with self._cv:
            self.closed = True
            self._cv.notify_all()


def test_each_frame_is_handed_over_when_it_arrives():
    """原来一次读 4096 字节、超时 0.1 秒：约 3 帧攒成一批，每 0.1 秒交出一次，同一批的帧带着同一个时刻
    （Pi 5 上录制的压力因此只有约 10 帧/秒）。每一帧都要在到达时交出，带着自己的时刻。"""
    port = PySerialPort()
    frames = []
    link = DeviceLink(frames.append, opener=lambda p: _ReadArrived(port), picker=lambda s: "/dev/fake")
    line = encode_sensor_frame(np.full(256, 4095)).encode()     # 约 1.3 KB，和满压力时真的帧一样长
    link.start()
    try:
        assert wait_for(lambda: link.connected)
        sent = []
        for _ in range(8):
            sent.append(time.monotonic())
            port.send(line)
            time.sleep(0.04)
        assert wait_for(lambda: len(frames) == 8)
    finally:
        link.stop()
    assert max(f.t - s for f, s in zip(frames, sent)) < 0.03
    assert len({f.t for f in frames}) == 8


def test_link_reconnects_after_unplug():
    esps = [FakeESP32(boot_lines=0), FakeESP32(boot_lines=0)]
    esps[0].fail_after = 3
    opened = []

    def opener(port):
        opened.append(port)
        return esps[len(opened) - 1]

    frames, events = [], []
    link = DeviceLink(frames.append, opener=opener, picker=lambda s: "/dev/fake",
                      on_event=lambda lvl, txt: events.append(txt))
    link.start()
    try:
        assert wait_for(lambda: len(opened) == 2 and esps[1].sent > 2, timeout=4)
        assert "控制器断开，正在重连" in events
    finally:
        link.stop()


def test_no_port_reports_problem():
    link = DeviceLink(lambda f: None, picker=lambda s: None)
    link.start()
    try:
        assert wait_for(lambda: link.problem == "没有找到控制器的 USB 串口")
        assert link.status()["connected"] is False
    finally:
        link.stop()


def test_boot_timeout_logs_what_arrived(monkeypatch, caplog):
    import logging
    import soundmat.device as dev
    monkeypatch.setattr(dev, "BOOT_WAIT_SECONDS", 0.3)
    esp = FakeESP32(boot_lines=10**6)             # 一直只发调试行，不进主循环
    link = DeviceLink(lambda f: None, opener=lambda p: esp, picker=lambda s: "/dev/fake")
    with caplog.at_level(logging.INFO, logger="soundmat.device"):
        link.start()
        try:
            assert wait_for(lambda: any("等控制器超时" in r.message for r in caplog.records), timeout=3)
        finally:
            link.stop()
    msg = next(r.message for r in caplog.records if "等控制器超时" in r.message)
    assert "字节" in msg and "# booting" in msg


class Garbled:
    """波特率不对的串口：不停地来字节，没有一行能认出来。"""
    closed = False

    def read(self, size):
        time.sleep(0.01)
        return b"\x0cp\x8c\xf0\x0c|"

    def write(self, data):
        return len(data)

    def close(self):
        self.closed = True


class Resetting(FakeESP32):
    """刚被复位的 ESP32：头一下是启动乱码，然后安静一阵（开机灯效），再开始发帧。"""

    def __init__(self, quiet: float):
        super().__init__(boot_lines=0)
        self.t0 = time.time()
        self.quiet = quiet
        self.burst = True

    def read(self, size):
        if self.burst:
            self.burst = False
            return b"\x00\x80\x80\x00" * 200
        if time.time() - self.t0 < self.quiet:
            time.sleep(0.01)
            return b""
        return super().read(size)


def test_link_reopens_when_everything_is_garbled(monkeypatch):
    import soundmat.device as dev
    monkeypatch.setattr(dev, "GARBLED_SECONDS", 0.2)
    ports = [Garbled(), FakeESP32(boot_lines=0)]
    opened = []

    def opener(port):
        opened.append(port)
        return ports[len(opened) - 1]

    frames, events = [], []
    link = DeviceLink(frames.append, opener=opener, picker=lambda s: "/dev/fake",
                      on_event=lambda lvl, txt: events.append(txt))
    link.start()
    try:
        assert wait_for(lambda: len(frames) >= 3, timeout=3)
        assert len(opened) == 2 and ports[0].closed
        assert "控制器断开，正在重连" not in events      # 还没连上过，不算断线
    finally:
        link.stop()


def test_link_waits_out_the_reset_burst(monkeypatch):
    """复位后的启动乱码之后安静一阵：不能当成乱码重开，否则又把 ESP32 复位。"""
    import soundmat.device as dev
    monkeypatch.setattr(dev, "GARBLED_SECONDS", 0.3)
    esp = Resetting(quiet=0.8)
    opened, frames = [], []
    link = DeviceLink(frames.append, opener=lambda p: opened.append(p) or esp, picker=lambda s: "/dev/fake")
    link.start()
    try:
        assert wait_for(lambda: len(frames) >= 3, timeout=3)
        assert len(opened) == 1
    finally:
        link.stop()
