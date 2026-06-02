"""ESP32 串口 auto 选口（无硬件）。"""
from soundmat.core.esp32_serial import _port_score, list_serial_ports, pick_serial_port


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
