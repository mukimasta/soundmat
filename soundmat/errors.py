"""给人看的错误：消息直接显示在控制台上。

各模块拒绝一个请求时抛出这里的错误（或它们的子类，例如编排的 ``LoadError``），控制接口统一按
``status`` 转成 HTTP 状态码，不需要每个接口各写一遍转换。
"""
from __future__ import annotations


class UserError(Exception):
    """请求做不到，原因写在消息里。"""
    status = 422


class InvalidRequest(UserError, ValueError):
    """请求里的值不合法，例如超出范围的声道或设置。"""
    status = 422


class Conflict(UserError):
    """当前状态下不能这样做，例如已经在录制、正在更新。"""
    status = 409


class NotFound(UserError):
    status = 404
