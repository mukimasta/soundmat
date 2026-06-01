"""模式协议。任何模式实现 start/stop/status/set_param 即可被 ModeManager 管理。"""

from .base import ModeApp

__all__ = ["ModeApp"]
