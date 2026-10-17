import time

import numpy as np
import pytest

from soundmat.device import DeviceLink
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
