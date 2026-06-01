"""LED 渲染：输出 108 路 RGB，状态机各分支不崩。"""
from soundmat import config
from soundmat.jam.led.renderer import JamLedRenderer
from soundmat.jam.led.layers import led_index_for_sector


def test_render_shape_all_states():
    r = JamLedRenderer()
    for playing, ended in [(False, False), (True, False), (False, True)]:
        buf = r.render(1.0, sweep_angle=-1.57, playing=playing, form_ended=ended,
                       control_count=2, stones=[(7, 0)])
        assert len(buf) == config.NUM_LEDS
        for px in buf:
            assert len(px) == 3
            assert all(0 <= c <= 255 for c in px)


def test_led_index_for_sector():
    assert led_index_for_sector(0) == 0
    assert led_index_for_sector(32) == 0
    # 8 扇区 = 1/4 圈 → 27 颗（卡位）
    assert led_index_for_sector(8) == 27


def test_scan_hit_lights_up():
    r = JamLedRenderer()
    r.on_scan_hit(0, 7, now=1.0)
    buf = r.render(1.0, sweep_angle=-1.57, playing=True, form_ended=False,
                   control_count=2, stones=[])
    center = led_index_for_sector(0)
    assert sum(buf[center]) > 0  # 命中中心应点亮
