"""LED 输出：把 108 路 RGB buffer 编码成 L 帧通过串口发回 ESP32。"""

from .writer import LEDWriter, encode_led_frame

__all__ = ["LEDWriter", "encode_led_frame"]
