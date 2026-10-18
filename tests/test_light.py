import numpy as np

from soundmat.config import LightConfig
from soundmat.exchange import Latest
from soundmat.light import LightEngine, composite, to_physical
from soundmat.sonification.intent import LightIntent, LightLayer


def layer(name, prio, rgb, alpha, n=108):
    return LightLayer(name, prio, np.tile(np.array(rgb, dtype=np.float32), (n, 1)), np.full(n, alpha, dtype=np.float32))


def test_composite_orders_by_priority():
    out = composite([layer("top", 5, (1, 0, 0), 1.0), layer("base", 0, (0, 0, 1), 1.0)], 108)
    assert tuple(out[0]) == (255, 0, 0)
    half = composite([layer("base", 0, (1, 1, 1), 0.5)], 108)
    assert tuple(half[0]) == (128, 128, 128)


def test_physical_offset_rotates():
    c = np.zeros((108, 3), dtype=np.uint8)
    c[0] = (255, 0, 0)
    p = to_physical(c, 101)
    assert tuple(p[101]) == (255, 0, 0) and tuple(p[0]) == (0, 0, 0)


def test_engine_sends_physical_and_previews_logical_with_system_layer():
    sent = []
    intent = Latest(LightIntent((layer("base", 0, (0, 0, 1), 1.0),)))
    eng = LightEngine(LightConfig(led_count=108, led_offset=101), intent, send=sent.append)
    one = np.zeros((108, 3), dtype=np.float32)
    one[0] = (1, 1, 1)
    a = np.zeros(108, dtype=np.float32)
    a[0] = 1
    eng.set_system_layer("countdown", LightLayer("countdown", 100, one, a))
    colors = eng.render(0.0)
    assert tuple(colors[0]) == (255, 255, 255) and tuple(colors[1]) == (0, 0, 255)
    assert tuple(sent[0][101]) == (255, 255, 255)
    hex_colors = eng.preview.get()["colors"]
    assert len(hex_colors) == 108 * 6
    assert hex_colors[:12] == "ffffff0000ff"
    eng.set_system_layer("countdown", None)
    assert tuple(eng.render(1.0)[0]) == (0, 0, 255)


def test_preview_follows_every_changed_frame_and_skips_unchanged():
    intent = Latest(LightIntent((layer("base", 0, (0, 0, 1), 1.0),)))
    eng = LightEngine(LightConfig(led_count=108, led_offset=0), intent)
    _, v0 = eng.preview.get_versioned()
    eng.render(0.0)
    eng.render(1 / 60)                       # 颜色没变：不更新预览
    _, v1 = eng.preview.get_versioned()
    assert v1 == v0 + 1
    intent.set(LightIntent((layer("base", 0, (1, 0, 0), 1.0),)))
    eng.render(2 / 60)                       # 下一帧就反映到预览，不按 30 Hz 降频
    colors, v2 = eng.preview.get_versioned()
    assert v2 == v1 + 1 and colors["colors"].startswith("ff0000")
    assert eng.rate.rate(2 / 60) == 3


def test_running_engine_renders_every_new_intent():
    """声音化交出的每一份新灯光意图都会被合成：两个 60 Hz 时钟错开时也不漏帧。"""
    import time

    intent = Latest(LightIntent())
    eng = LightEngine(LightConfig(led_count=108, led_offset=0), intent)
    seen = []
    eng.preview.subscribe(lambda: seen.append(eng.preview.get()["colors"][:6]))
    eng.start()
    try:
        for i in range(1, 31):
            intent.set(LightIntent((layer("base", 0, (i / 255, 0, 0), 1.0),)))
            time.sleep(1 / 60)
        time.sleep(0.05)
    finally:
        eng.stop()
    assert [c for c in seen if c != "000000"] == [f"{i:02x}0000" for i in range(1, 31)]


def test_refresh_rate_caps_frames_even_with_60_hz_intents():
    """刷新率设成 30 时，即使声音化每秒交出 60 份新意图，灯光也只合成约 30 帧。"""
    import time

    intent = Latest(LightIntent())
    eng = LightEngine(LightConfig(led_count=108, led_offset=0, refresh_hz=30), intent)
    eng.start()
    try:
        t0 = time.monotonic()
        i = 0
        while time.monotonic() - t0 < 1.0:
            i += 1
            intent.set(LightIntent((layer("base", 0, ((i % 255) / 255, 0, 0), 1.0),)))
            time.sleep(1 / 60)
    finally:
        eng.stop()
    assert 25 <= eng.frames <= 42          # 约 30 帧（上限留了抖动余量），远低于 60
