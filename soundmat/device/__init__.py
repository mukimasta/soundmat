"""设备连接：与压力垫与灯环控制器（ESP32）的 USB 串口链路（ARCHITECTURE「设备连接」）。

职责：解析和校验压力帧、编码灯光帧、开机时等待控制器就绪、断线后自动重连，并报告链路健康
（是否连接、实测帧率、校验错误数）。

沿用第一版的串口细节：打开时 DTR、RTS 置低，避免 USB 串口芯片把 ESP32 复位；ESP32 开机灯效期间
不发 S 帧，要等到第一帧 ``S:`` 才开始发送灯光帧；连上后的第一帧灯光发两次，防止开机窗口丢包。
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Protocol

import numpy as np

from ..timebase import system_time
from .ports import pick_port
from .protocol import BAUD, FrameError, encode_led_frame, parse_sensor_frame

log = logging.getLogger("soundmat.device")

RETRY_SECONDS = 2.0       # 打不开或断线后多久重试
SILENCE_SECONDS = 5.0     # 已经收到过 S 帧之后，这么久没有新的 S 帧：关掉重开
# 刚打开串口时等第一帧 S 帧的时间。打开串口可能让 ESP32 复位，固件开机后约 5 秒的灯效期间不发
# S 帧；如果这里也只等 5 秒，每次重开都会在它开完机之前再次复位它，永远等不到（Pi 3B 上实测）
BOOT_WAIT_SECONDS = 15.0
# 打开串口这么久之后还在不断收到字节、却没有一行能认出来（# 开头的调试行或 S 帧）：串口芯片的设置
# 没生效，关掉马上重开。Pi 断电重启后第一次打开串口时，CP2102 常常既没设成 921600 波特、也没把
# ESP32 复位，收到的全是波特率不对的乱码（2026-10-20 Pi 5 上实测，原来要白等 15 秒）；重开就好。
# ESP32 被复位时只在头 0.1 秒左右有一阵启动乱码，之后安静到开机灯效结束，不会落进这条。
GARBLED_SECONDS = 2.0


class _Garbled(Exception):
    """一直在收字节，却没有一行能认出来。"""


class SerialLike(Protocol):
    def read(self, size: int) -> bytes: ...
    def write(self, data: bytes) -> int | None: ...
    def close(self) -> None: ...


def open_serial(port: str) -> SerialLike:
    import serial

    ser = serial.Serial()
    ser.port = port
    ser.baudrate = BAUD
    ser.timeout = 0.1
    ser.write_timeout = 1.0
    ser.dtr = False
    ser.rts = False
    ser.open()
    time.sleep(0.15)
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    return ser


@dataclass(frozen=True)
class RawFrame:
    t: float
    seq: int
    values: np.ndarray        # 256 个 ADC 读数，环优先的接线顺序


class _BootDiag:
    """打开串口后、收到第一帧 S 帧之前收到了什么；等控制器超时时写进日志，用来查为什么没有就绪。"""

    def __init__(self, opened: float):
        self.opened = opened
        self.bytes = 0
        self.first_at: float | None = None
        self.last_at: float | None = None
        self.head = b""
        self.tail = b""
        self.comments: list[str] = []
        self.bad_frames = 0
        self.readable = False      # 收到过能认出来的一行（调试行或 S 帧，校验不过的也算）

    def add(self, chunk: bytes, now: float) -> None:
        if self.first_at is None:
            self.first_at = now
        self.last_at = now
        self.bytes += len(chunk)
        if len(self.head) < 60:
            self.head += chunk[:60 - len(self.head)]
        self.tail = (self.tail + chunk)[-60:]

    def summary(self) -> str:
        if not self.bytes:
            return "打开后一个字节都没有收到"
        t = lambda x: f"{x - self.opened:.1f} 秒"
        return (f"收到 {self.bytes} 字节（第一个在 {t(self.first_at)}，最后一个在 {t(self.last_at)}），"
                f"坏的 S 帧 {self.bad_frames} 行，调试行 {self.comments[-5:]}，开头 {self.head!r}，结尾 {self.tail!r}")


class DeviceLink:
    def __init__(self, on_frame: Callable[[RawFrame], None], port: str = "auto",
                 opener: Callable[[str], SerialLike] = open_serial,
                 picker: Callable[[str], str | None] = pick_port,
                 on_event: Callable[[str, str], None] | None = None):
        self._on_frame = on_frame
        self._port_setting = port
        self._opener = opener
        self._picker = picker
        self._on_event = on_event or (lambda level, text: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._write_lock = threading.Lock()
        self._ser: SerialLike | None = None
        self._booted = False
        self._double_send = False
        self._boot_diag = _BootDiag(0.0)
        self._times: deque[float] = deque(maxlen=240)
        self.seq = 0
        self.port: str | None = None
        self.connected = False
        self.checksum_errors = 0
        self.last_frame = 0.0
        self.problem: str | None = "尚未连接"

    # ── 状态 ────────────────────────────────────────────────────────────

    def fps(self, now: float | None = None) -> float:
        """最近 1 秒的实测帧率。"""
        now = system_time() if now is None else now
        recent = [t for t in self._times if now - t <= 1.0]
        return float(len(recent))

    def status(self) -> dict:
        """给系统监测：控制器链路（CONTROL_API ``status.mat``）。"""
        now = system_time()
        return {
            "connected": self.connected and self._booted,
            "port": self.port,
            "fps": round(self.fps(now), 1),
            "checksumErrors": self.checksum_errors,
            "problem": self.problem,
            "source": "controller",
        }

    def rates(self) -> dict[str, dict]:
        """给系统监测：传感帧率由控制器决定，没有固定的期望值。"""
        return {"sensing": {"actual": self.fps(), "expected": None}}

    # ── 灯光 ────────────────────────────────────────────────────────────

    def send_leds(self, colors: np.ndarray) -> bool:
        """发送一帧灯光（物理顺序）；返回是否写给了控制器。控制器还没就绪时丢弃。"""
        ser = self._ser
        if ser is None or not self._booted:
            return False
        data = encode_led_frame(colors)
        try:
            with self._write_lock:
                ser.write(data)
                if self._double_send:
                    self._double_send = False
                    time.sleep(0.02)
                    ser.write(data)
            return True
        except Exception as e:  # 写失败：读线程会发现断线并重连
            log.debug("写灯光帧失败：%s", e)
            return False

    # ── 线程 ────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="device", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._close()

    def _close(self) -> None:
        ser, self._ser = self._ser, None
        self._booted = False
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass

    def _run(self) -> None:
        while not self._stop.is_set():
            port = self._picker(self._port_setting)
            if port is None:
                self._set_problem("没有找到控制器的 USB 串口")
                self._stop.wait(RETRY_SECONDS)
                continue
            try:
                ser = self._opener(port)
            except Exception as e:
                self._set_problem(f"无法打开 {port}：{e}")
                self._stop.wait(RETRY_SECONDS)
                continue
            self._ser, self.port, self.connected = ser, port, True
            self._booted = False
            self.problem = "等待控制器就绪"
            try:
                self._read_loop(ser)
            except _Garbled:
                log.info("串口收到的全是乱码（%s），重新打开", self._boot_diag.summary())
                self._close()
                self.connected = False
                self._stop.wait(0.5)
                continue
            except Exception as e:
                if not self._stop.is_set():
                    log.debug("串口读取出错：%s", e)
            was_booted = self._booted
            if not was_booted and not self._stop.is_set():
                log.info("等控制器超时：%s", self._boot_diag.summary())
            self._close()
            self.connected = False
            if self._stop.is_set():
                break
            if was_booted:
                self._on_event("warning", "控制器断开，正在重连")
            self._set_problem("控制器断开，正在重连")
            self._stop.wait(RETRY_SECONDS / 2)

    def _set_problem(self, text: str) -> None:
        if text != self.problem:
            log.info(text)
        self.problem = text

    def _read_loop(self, ser: SerialLike) -> None:
        buf = b""
        opened = system_time()
        self._boot_diag = _BootDiag(opened)
        while not self._stop.is_set():
            chunk = ser.read(4096)
            now = system_time()
            if chunk:
                if not self._booted:
                    self._boot_diag.add(chunk, now)
                buf += chunk
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    self._line(raw.decode("ascii", errors="replace").strip(), now)
            if (not self._booted and not self._boot_diag.readable and now - opened > GARBLED_SECONDS
                    and self._boot_diag.last_at is not None and now - self._boot_diag.last_at < GARBLED_SECONDS / 4):
                raise _Garbled()
            last = self.last_frame if self._booted else opened
            limit = SILENCE_SECONDS if self._booted else BOOT_WAIT_SECONDS
            if now - max(last, opened) > limit:
                raise TimeoutError("控制器没有数据")

    def _line(self, text: str, now: float) -> None:
        if not text:
            return
        if not text.startswith(("S:", "#")):
            # ESP32 复位时的启动乱码不一定以换行结尾，会和后面第一行粘在一起：从行里最后一处开头算起
            i = max(text.rfind("S:"), text.rfind("# "))
            if i > 0:
                text = text[i:]
        if text.startswith("#"):
            log.debug("控制器：%s", text)
            if not self._booted:
                self._boot_diag.comments.append(text[:60])
                self._boot_diag.readable = True
            return
        if not text.startswith("S:"):
            return
        self._boot_diag.readable = True
        try:
            values = parse_sensor_frame(text)
        except FrameError:
            self.checksum_errors += 1
            if not self._booted:
                self._boot_diag.bad_frames += 1
            return
        if not self._booted:
            self._booted = True
            self._double_send = True
            self.problem = None
            self._on_event("info", f"控制器已连接（{self.port}）")
        self.seq += 1
        self.last_frame = now
        self._times.append(now)
        self._on_frame(RawFrame(now, self.seq, values))
