"""Web 控制台：FastAPI，切换模式、启停、调参、传感热力图、事件流。

装置上无物理按钮（保持美学纯粹）；开发/调试/Demo 通过手机扫码访问这个轻量 HTTP 服务。
直接持有 ModeManager 引用，方法调用而非 IPC。
"""

from .server import run_web, build_app

__all__ = ["run_web", "build_app"]
