"""假的 scsynth：回答 /status、/d_loadDir、/n_query，记录收到的消息和 bundle 时间戳。"""
from __future__ import annotations

import socket
import struct
import threading

from pythonosc.osc_bundle import OscBundle
from pythonosc.osc_message import OscMessage
from pythonosc.osc_message_builder import OscMessageBuilder

NTP_EPOCH = 2208988800


def reply(address, *args):
    b = OscMessageBuilder(address)
    for a in args:
        b.add_arg(a)
    return b.build().dgram


class FakeScsynth:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.05)
        self.port = self.sock.getsockname()[1]
        self.messages: list[tuple[float | None, str, list]] = []   # (bundle 墙钟时间戳或 None, 地址, 参数)
        self.client = None
        self.alive = True
        self.nodes_lost = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()
        self._thread.join(timeout=1)
        self.sock.close()

    def of(self, address):
        return [m for m in self.messages if m[1] == address]

    def send(self, data):
        if self.client:
            self.sock.sendto(data, self.client)

    def _run(self):
        while not self._stop.is_set():
            try:
                data, addr = self.sock.recvfrom(65536)
            except (socket.timeout, OSError):
                continue
            if not self.alive:
                continue
            self.client = addr
            if data.startswith(b"#bundle"):
                secs, frac = struct.unpack(">II", data[8:16])
                stamp = None if (secs, frac) == (0, 1) else secs - NTP_EPOCH + frac / 2**32
                for m in OscBundle(data):
                    self._msg(stamp, m)
            else:
                self._msg(None, OscMessage(data))

    def _msg(self, stamp, m):
        args = list(m.params)
        self.messages.append((stamp, m.address, args))
        if m.address == "/status":
            self.send(reply("/status.reply", 1, 0, 0, 1, 60, 1.5, 2.0, 48000.0, 48000.0))
        elif m.address == "/d_loadDir":
            self.send(reply("/done", "/d_loadDir"))
        elif m.address == "/n_query" and self.nodes_lost:
            self.nodes_lost = False
            self.send(reply("/fail", "/n_query", "Node 100 not found"))
