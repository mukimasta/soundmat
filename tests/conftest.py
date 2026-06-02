"""测试默认关闭 slice 镜像（Mock 垫 / 单元测试用 CW wire 坐标）。"""
import pytest

from soundmat import config


@pytest.fixture(autouse=True)
def _wire_slice_no_mirror():
    prev = config.WIRE_SLICE_MIRROR
    config.WIRE_SLICE_MIRROR = False
    yield
    config.WIRE_SLICE_MIRROR = prev
