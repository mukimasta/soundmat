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
# 刚打开串口时这么久连一个字节都没有收到：关掉马上重开，不等满 BOOT_WAIT_SECONDS。ESP32 开机后不停地发
# S 帧，不管有没有人读；Pi 开机时串口要三十多秒后才有人打开，这期间 USB 串口芯片（CP2102）被灌满，
# 第一次打开常常一个字节也收不到（关闭时内核报 cp210x "failed set request 0x12 status: -110"），
# 关掉重开就好（2026-10-19 Pi 5 上两次开机都是这样，白等 15 秒）。打开串口让 ESP32 复位时，
# 它马上会发开机信息，有字节，所以不会落进这里、反复复位它。
NO_DATA_SECONDS = 3.0


class _NoData(Exception):
    """刚打开串口后一个字节都没有收到。"""


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
            except _NoData:
                self._close()
                self.connected = False
                log.info("打开串口后 %.0f 秒没有收到任何数据，重新打开", NO_DATA_SECONDS)
                self._stop.wait(0.5)
                continue
            except Exception as e:
                if not self._stop.is_set():
                    log.debug("串口读取出错：%s", e)
            was_booted = self._booted
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
        got_bytes = False
        while not self._stop.is_set():
            chunk = ser.read(4096)
            now = system_time()
            if chunk:
                got_bytes = True
                buf += chunk
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    self._line(raw.decode("ascii", errors="replace").strip(), now)
            if not got_bytes and now - opened > NO_DATA_SECONDS:
                raise _NoData()
            last = self.last_frame if self._booted else opened
            limit = SILENCE_SECONDS if self._booted else BOOT_WAIT_SECONDS
            if now - max(last, opened) > limit:
                raise TimeoutError("控制器没有数据")

    def _line(self, text: str, now: float) -> None:
        if not text:
            return
        if text.startswith("#"):
            log.debug("控制器：%s", text)
            return
        if not text.startswith("S:"):
            return
        try:
            values = parse_sensor_frame(text)
        except FrameError:
            self.checksum_errors += 1
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
