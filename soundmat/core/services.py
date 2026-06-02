"""SharedServices：把所有共享底层服务打包传给模式 app。

模式 app 拿到这个就能访问 SC 服务器、传感器、LED、OSC，但不需要知道它们怎么实例化的。
"""
from __future__ import annotations

from dataclasses import dataclass

from .led.writer import LEDWriter
from .osc import OSCClient
from .sc_server import SCServerHandle
from .sensor.reader import SensorReader


@dataclass
class SharedServices:
    sc: SCServerHandle      # 控制 scsynth（new_group / free_group / load defs / buffers）
    sensor: SensorReader    # 订阅 / 拉取传感数据
    leds: LEDWriter         # 提供 LED buffer
    osc: OSCClient          # 发 OSC 给 scsynth（s_new / n_set / n_free）
    serial_port: str | None = None
    serial_ready: bool = False
