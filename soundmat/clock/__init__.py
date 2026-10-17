"""时钟：全系统统一的时间基准（DATA_MODEL「所有运行时数据使用同一个单调递增的时间基准」）。"""
from __future__ import annotations

import time


def system_time() -> float:
    """系统时间：单调递增，单位秒。"""
    return time.monotonic()
