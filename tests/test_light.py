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
    assert eng.preview.get()["colors"][0] == [255, 255, 255]
    eng.set_system_layer("countdown", None)
    assert tuple(eng.render(1.0)[0]) == (0, 0, 255)
