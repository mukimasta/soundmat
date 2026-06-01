"""S 帧解析 + 校验 + L 帧编码往返。"""
import numpy as np

from soundmat import config
from soundmat.core.led.writer import encode_led_frame
from soundmat.core.sensor.frame import (
    FrameError,
    compute_checksum,
    parse_sensor_frame,
    values_to_matrix,
)


def build_s_frame(values):
    payload = ",".join(str(v) for v in values)
    body = f"S:{payload}"
    chk = compute_checksum(body.encode("ascii"))
    return f"{body}*{chk:02X}"


def test_parse_roundtrip():
    values = [(i % 4096) - 1 for i in range(config.SENSOR_VALUES)]  # 含 -1
    line = build_s_frame(values)
    parsed = parse_sensor_frame(line)
    assert len(parsed) == config.SENSOR_VALUES
    assert list(parsed) == values
    m = values_to_matrix(parsed)
    assert m.shape == (config.NUM_RINGS, config.NUM_SLICES)


def test_checksum_failure_raises():
    values = [0] * config.SENSOR_VALUES
    line = build_s_frame(values)
    bad = line[:-2] + "FF"   # 篡改校验码
    try:
        parse_sensor_frame(bad)
        assert False, "应抛 FrameError"
    except FrameError:
        pass


def test_wrong_count_raises():
    line = build_s_frame([0] * 10)
    try:
        parse_sensor_frame(line)
        assert False
    except FrameError:
        pass


def test_led_frame_encode():
    buf = [(255, 0, 0)] * config.NUM_LEDS
    frame = encode_led_frame(buf)
    assert frame.startswith("L:FF0000,")
    assert frame.endswith("\n")
    star = frame.index("*")
    body = frame[:star]
    chk = int(frame[star + 1:].strip(), 16)
    assert chk == compute_checksum(body.encode("ascii"))
    assert frame.count(",") == config.NUM_LEDS - 1
