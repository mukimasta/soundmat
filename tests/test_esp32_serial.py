"""ESP32 串口 auto 选口（无硬件）。"""
import pytest

from soundmat.core.esp32_serial import (
    _port_score,
    is_linux_onboard_uart,
    list_serial_ports,
    pick_serial_port,
)


def test_port_score_prefers_usbserial():
    a = _port_score("/dev/cu.usbserial-1410")
    b = _port_score("/dev/cu.debug-console")
    assert a[0] < b[0]  # lower sort key = higher priority


def test_list_serial_ports_filters_bluetooth():
    ports = list_serial_ports()
    for p in ports:
        assert "bluetooth" not in p.lower()


def test_pick_serial_port_explicit():
    assert pick_serial_port("/dev/ttyUSB0") == "/dev/ttyUSB0"


@pytest.mark.parametrize(
    "path",
    ["/dev/ttyS0", "/dev/ttyS1", "/dev/ttyAMA0", "/dev/ttyAMA10", "/dev/serial0", "/dev/serial1"],
)
def test_is_linux_onboard_uart_true(path, monkeypatch):
    monkeypatch.setattr("soundmat.core.esp32_serial.sys.platform", "linux")
    assert is_linux_onboard_uart(path)


@pytest.mark.parametrize("path", ["/dev/ttyUSB0", "/dev/ttyACM0", "/dev/serial/by-id/usb-X"])
def test_is_linux_onboard_uart_false_for_usb(path, monkeypatch):
    monkeypatch.setattr("soundmat.core.esp32_serial.sys.platform", "linux")
    assert not is_linux_onboard_uart(path)


def test_is_linux_onboard_uart_not_applied_on_darwin(monkeypatch):
    monkeypatch.setattr("soundmat.core.esp32_serial.sys.platform", "darwin")
    assert not is_linux_onboard_uart("/dev/ttyS0")


def test_list_serial_ports_excludes_linux_onboard(monkeypatch):
    monkeypatch.setattr("soundmat.core.esp32_serial.sys.platform", "linux")

    class _Port:
        def __init__(self, device: str):
            self.device = device

    monkeypatch.setattr(
        "serial.tools.list_ports.comports",
        lambda: [_Port("/dev/ttyS0"), _Port("/dev/ttyUSB0"), _Port("/dev/ttyAMA0")],
    )
    monkeypatch.setattr("soundmat.core.esp32_serial._glob_candidates", lambda: [])

    ports = list_serial_ports()
    assert ports == ["/dev/ttyUSB0"]


def test_pick_serial_port_auto_prefers_usb_over_onboard(monkeypatch):
    monkeypatch.setattr("soundmat.core.esp32_serial.sys.platform", "linux")

    class _Port:
        def __init__(self, device: str):
            self.device = device

    monkeypatch.setattr(
        "serial.tools.list_ports.comports",
        lambda: [_Port("/dev/ttyS0"), _Port("/dev/ttyUSB0")],
    )
    monkeypatch.setattr("soundmat.core.esp32_serial._glob_candidates", lambda: [])

    assert pick_serial_port("auto") == "/dev/ttyUSB0"
