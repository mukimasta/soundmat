"""按需启动合成器服务（docs/implementation/SYNTH.md「启动」）。

树莓派上 scsynth 是独立的 systemd 服务，主机程序只去连接它：主机程序重启时声音链路不中断，
两边出错时各自恢复。开发机上这样要多开一个终端，所以 ``uv run soundmat`` 启动时先看配置的
端口上有没有 scsynth 在响应：有就直接连（systemd 服务、手动启动的都算）；没有就自己启动一个，
退出时一起关掉。在 systemd 下运行时从不自己启动，避免和 scsynth 服务抢同一个端口。
"""
from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
import threading
from pathlib import Path

log = logging.getLogger("soundmat.scsynth")

MAC_SCSYNTH = "/Applications/SuperCollider.app/Contents/Resources/scsynth"
_STATUS = b"/status\x00,\x00\x00\x00"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def responding(host: str, port: int, timeout: float = 0.3) -> bool:
    """这个地址上是否有合成器服务回应 /status。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(_STATUS, (host, port))
        s.recvfrom(1024)
        return True
    except OSError:
        return False
    finally:
        s.close()


def find_scsynth() -> str | None:
    """scsynth 的位置：环境变量 SOUNDMAT_SCSYNTH，否则 PATH 里的 scsynth，否则 macOS 的 SuperCollider.app。"""
    env = os.environ.get("SOUNDMAT_SCSYNTH")
    if env:
        return env
    found = shutil.which("scsynth")
    if found:
        return found
    return MAC_SCSYNTH if Path(MAC_SCSYNTH).exists() else None


def under_systemd() -> bool:
    return bool(os.environ.get("INVOCATION_ID"))


class ScsynthProcess:
    """主机程序自己启动的 scsynth；``stop`` 时一起关掉。"""

    def __init__(self, port: int, channels: int = 2, sample_rate: int = 48000, binary: str | None = None):
        self.port = port
        self.channels = channels
        self.sample_rate = sample_rate
        self.binary = binary
        self.proc: subprocess.Popen | None = None
        self._ready = threading.Event()

    def command(self) -> list[str]:
        # 与 scripts/scsynth-dev.sh 相同：只开输出，采样率与声音素材一致
        return [self.binary or "scsynth", "-u", str(self.port), "-i", "0", "-o", str(self.channels),
                "-S", str(self.sample_rate)]

    def start(self, timeout: float = 10.0) -> bool:
        """启动并等它打印 server ready。返回是否就绪；没就绪也不结束进程，主机程序会继续重连。"""
        self.proc = subprocess.Popen(self.command(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, bufsize=1)
        threading.Thread(target=self._pump, name="scsynth-log", daemon=True).start()
        return self._ready.wait(timeout)

    def _pump(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            line = line.rstrip()
            if "server ready" in line:
                self._ready.set()
            if line:
                log.debug("%s", line)
        code = self.proc.wait()
        if not self._ready.is_set() or code not in (0, -15):
            log.warning("合成器服务退出（代码 %s）", code)

    def stop(self) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def ensure_scsynth(host: str, port: int, channels: int, sample_rate: int) -> ScsynthProcess | None:
    """配置的端口上没有 scsynth 时自己启动一个。返回自己启动的进程（退出时要关掉），否则 None。"""
    if responding(host, port):
        log.info("连接已在运行的合成器服务 %s:%s", host, port)
        return None
    if host not in LOCAL_HOSTS:
        log.warning("合成器服务 %s:%s 没有回应；它不在本机，不自动启动", host, port)
        return None
    if under_systemd():
        log.warning("合成器服务 %s:%s 没有回应；在 systemd 下运行时由 scsynth 服务负责，不自动启动", host, port)
        return None
    binary = find_scsynth()
    if binary is None:
        log.warning("没有找到 scsynth（可设置 SOUNDMAT_SCSYNTH 指定位置），声音不会发声")
        return None
    proc = ScsynthProcess(port, channels, sample_rate, binary)
    if proc.start():
        log.info("已启动合成器服务（%s 声道，%g kHz），退出时一起关闭", channels, sample_rate / 1000)
    else:
        log.warning("合成器服务启动后 10 秒内没有就绪；会继续尝试连接。可单独运行 scripts/scsynth-dev.sh 查看原因")
    return proc
