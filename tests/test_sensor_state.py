"""SensorState：R0/R1 控制值映射。"""
import numpy as np

from soundmat.jam.event.sensor_state import SensorState


def test_control_value_linear_min_max():
    st = SensorState(threshold=0, control_min=0, control_max=1000)
    m = np.zeros((8, 32), dtype=np.int16)
    m[0, 0] = 500
    delta = st.update(m)
    assert delta.control_value == 500.0

    m[0, 0] = 1000
    delta = st.update(m)
    assert delta.control_value == 1000.0

    m[0, 0] = 2000
    delta = st.update(m)
    assert delta.control_value == 1000.0


def test_control_value_respects_min():
    st = SensorState(threshold=0, control_min=200, control_max=1000)
    m = np.zeros((8, 32), dtype=np.int16)
    m[0, 0] = 100
    assert st.update(m).control_value == 0.0
    m[0, 0] = 600
    assert st.update(m).control_value == 500.0
