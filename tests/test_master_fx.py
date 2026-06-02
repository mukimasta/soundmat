"""MasterFX Lo-Fi 平滑。"""
from soundmat.jam.bridge.master_fx import _smooth_lofi_step


def test_smooth_reaches_zero_and_full():
    v = 500.0
    for _ in range(80):
        v = _smooth_lofi_step(v, 1000.0)
    assert v >= 998.0

    for _ in range(80):
        v = _smooth_lofi_step(v, 0.0)
    assert v <= 2.0


def test_smooth_monotonic_up():
    v = 0.0
    prev = v
    for _ in range(40):
        v = _smooth_lofi_step(v, 500.0)
        assert v >= prev
        prev = v
