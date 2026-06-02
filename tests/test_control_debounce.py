"""控制石 sum 判 active + 释放延时。"""
import numpy as np

from soundmat import config
from soundmat.jam.event.sensor_state import SensorState


def test_control_active_uses_sum_not_single_cell():
    st = SensorState(threshold=300, control_sum_min=200)
    m = np.zeros((8, 32), dtype=np.int16)
    m[0, 0] = 150  # 单格有压力但 sum 不足
    assert st.update(m).control_active is False
    m[0, 2] = 100  # sum=250
    assert st.update(m).control_active is True


def test_control_sum_min_configurable():
    st = SensorState(threshold=0, control_sum_min=500)
    m = np.zeros((8, 32), dtype=np.int16)
    m[0, 0] = 400
    assert st.update(m).control_active is False


def test_jam_effective_control_hold():
    from soundmat.jam.app import JamApp

    app = JamApp.__new__(JamApp)
    app._last_control_active = True
    app._control_inactive_since = None
    config.CONTROL_RELEASE_HOLD_SEC = 0.1

    assert app._effective_control_active(True, 1.0) is True
    assert app._control_inactive_since is None

    assert app._effective_control_active(False, 1.0) is True
    assert app._control_inactive_since == 1.0

    assert app._effective_control_active(False, 1.05) is True
    assert app._effective_control_active(False, 1.11) is False

    assert app._effective_control_active(True, 1.2) is True
    assert app._control_inactive_since is None
