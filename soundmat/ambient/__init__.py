"""Ambient 模式：公共艺术装置氛围环境音乐（《京都岚山》主题）。

数据流（设计文档 §5.2）：sensor → tracker → state → mapper → voices → engine → scsynth
"""

from .app import AmbientApp

__all__ = ["AmbientApp"]
