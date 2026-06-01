"""ModeApp 协议（设计文档 §12.1）。

不是严格的抽象基类，只是约定（duck typing）：任何模式只要实现这四个方法就能被
ModeManager 管理。模式自己起背景线程跑主循环、订阅传感器、注册 LED 数据源、在自己的
SC group 下 spawn synth。
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..core.services import SharedServices


@runtime_checkable
class ModeApp(Protocol):
    def __init__(self, manifest: dict, services: SharedServices) -> None: ...

    def start(self) -> None:
        """新建自己的 SC group，起初始 synth（如 master FX），订阅传感器，启动主循环线程。"""
        ...

    def stop(self) -> None:
        """停主循环线程，取消订阅，清空 LED 数据源，free 自己的 SC group。"""
        ...

    def status(self) -> dict:
        """返回当前状态字典（供 Web /api/status）。"""
        ...

    def set_param(self, key: str, value: Any) -> None:
        """运行时调参（如 jam 的 bpm、master_volume）。"""
        ...
