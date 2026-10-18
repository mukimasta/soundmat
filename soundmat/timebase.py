"""系统时间：全系统统一的时间基准（DATA_MODEL「节拍与时间窗」）。

所有运行时数据使用同一个单调递增的系统时间（秒），不受校时影响。这个模块不依赖任何其他模块，
所以时钟、速率计和各个线程都能直接使用，不会引起循环导入。
"""
from __future__ import annotations

import time


def system_time() -> float:
    """系统时间：单调递增，单位秒。"""
    return time.monotonic()
