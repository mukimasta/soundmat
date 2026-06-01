"""传感器输入：S 帧解析 + SensorReader 抽象（串口实现 / mock 回放实现）。"""

from .reader import SensorReader, SensorFrame
from .frame import parse_sensor_frame, FrameError

__all__ = ["SensorReader", "SensorFrame", "parse_sensor_frame", "FrameError"]
