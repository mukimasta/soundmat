"""让每个线程在操作系统里显示自己的名字（Linux），方便用 top -H、/proc 按线程看 CPU。

Python 的线程名（threading.Thread(name=...)）不会传给操作系统，所以在系统里所有线程都叫
``soundmat``，分不出声音化、灯光、设备连接各用了多少。``install()`` 之后，每个线程开始运行时
用 prctl(PR_SET_NAME) 把名字（最多 15 个字节）设给自己；不是 Linux 时什么都不做。
"""
from __future__ import annotations

import ctypes
import ctypes.util
import sys
import threading

PR_SET_NAME = 15
_installed = False


def set_os_thread_name(name: str) -> None:
    if not sys.platform.startswith("linux"):
        return
    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)
        libc.prctl(PR_SET_NAME, ctypes.c_char_p(name.encode()[:15]), 0, 0, 0)
    except OSError:
        pass


def install() -> None:
    global _installed
    if _installed:
        return
    _installed = True
    original = threading.Thread.run

    def run(self: threading.Thread) -> None:
        set_os_thread_name(self.name)
        original(self)

    threading.Thread.run = run
