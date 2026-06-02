"""LED 渲染：输出 108 路 RGB，状态机各分支不崩。"""
import time

from soundmat import config
from soundmat.core.led.offset import apply_led_offset
from soundmat.core.led.writer import LEDWriter
from soundmat.jam.led.renderer import JamLedRenderer
from soundmat.jam.led.layers import CARDINAL_LED_INDICES, led_index_for_angle, led_index_for_sector


def test_render_shape_all_states():
    r = JamLedRenderer()
    for playing, ended in [(False, False), (True, False), (False, True)]:
        buf = r.render(1.0, sweep_angle=-1.57, playing=playing, form_ended=ended,
                       control_count=2, stones=[(7, 0)])
        assert len(buf) == config.NUM_LEDS
        for px in buf:
            assert len(px) == 3
            assert all(0 <= c <= 255 for c in px)


def test_led_index_for_sector_logical():
    assert led_index_for_sector(0) == 0
    assert led_index_for_sector(32) == 0
    assert led_index_for_sector(8) == 27


def test_led_angle_aligns_with_sector():
    from soundmat.jam.scheduler.timing import sector_center_angle

    for sec in (0, 4, 8, 16, 24):
        angle = sector_center_angle(sec)
        assert led_index_for_angle(angle) == led_index_for_sector(sec)


def test_apply_led_offset_rotates():
    logical = [(0, 0, 0)] * config.NUM_LEDS
    logical[0] = (255, 0, 0)
    physical = apply_led_offset(logical, offset=10)
    assert physical[10] == (255, 0, 0)
    assert physical[0] == (0, 0, 0)


def test_apply_led_offset_cardinals():
    logical = [(0, 0, 0)] * config.NUM_LEDS
    for i in (0, 27, 54, 81):
        logical[i] = (255, 140, 140)
    physical = apply_led_offset(logical, offset=10)
    for i in (10, 37, 64, 91):
        assert physical[i] == (255, 140, 140)


def test_idle_breath_max_brightness():
    r = JamLedRenderer()
    non_card = [i for i in range(config.NUM_LEDS) if i not in CARDINAL_LED_INDICES]
    for t in (0.0, 0.5, 1.0, 2.3, 5.7):
        buf = r.render(t, sweep_angle=0, playing=False, form_ended=False)
        assert max(c for i in non_card for c in buf[i]) <= 20


def test_cardinal_breath_75_100():
    r = JamLedRenderer()
    lo = int(255 * 0.75) - 2
    for t in (0.0, 0.5, 1.0, 2.3, 5.7):
        for playing, ended in ((False, False), (True, False), (False, True)):
            buf = r.render(t, sweep_angle=0, playing=playing, form_ended=ended)
            for i in CARDINAL_LED_INDICES:
                assert max(buf[i]) >= lo
                assert max(buf[i]) <= 255


def test_led_serial_lost_fires_once():
    import threading

    class _BadSerial:
        def write(self, _data):
            raise OSError(6, "Device not configured")

        def flush(self):
            pass

    lost = threading.Event()
    w = LEDWriter(fps=200.0, on_serial_lost=lost.set)
    w.attach_serial(_BadSerial())
    w.start()
    time.sleep(0.05)
    w.stop()
    assert lost.is_set()


def test_scan_hit_lights_up_logical():
    r = JamLedRenderer()
    r.on_scan_hit(0, 7, now=1.0)
    buf = r.render(1.0, sweep_angle=-1.57, playing=True, form_ended=False,
                   control_count=2, stones=[])
    assert sum(buf[0]) > 0
