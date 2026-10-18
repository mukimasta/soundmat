"""合成器服务（scsynth）的实现：把声音引擎的抽象指令变成带时间戳的 OSC bundle。

分两层：

- ``ScsynthCommands`` 把引擎的指令翻译成 scsynth 的 OSC 指令，并给节点、总线和缓冲区编号记账。它不关心
  指令怎样送到合成器服务，所有指令只经两个出口交出：``send``（立即执行）和 ``schedule``（在某个时刻执行）。
  这两个出口就是扩展点：离线渲染（scripts/render.py）用同一套翻译，把指令记成 scsynth 的非实时乐谱。
- ``ScsynthBackend`` 是实时连接。scsynth 是独立的系统服务（TECH_STACK「合成器服务」），主机程序只通过
  UDP 与它通信：

  - 每一拍里引擎发出的指令按执行时刻分组，一拍结束时整批发出；时刻是系统时间（单调时钟），
    发送时换算成墙钟时间作为 bundle 的时间戳。时刻已到的指令用"立即执行"的时间戳，避免 scsynth
    记录迟到警告。
  - 墙钟在 scsynth 运行时跳变（树莓派没有电池时钟，联网校时会一下跳几分钟），它要一分多钟才重新
    对齐，期间定时全乱。所以开机时先等校时再启动声音、之后不再校时（system/clock/，
    DEPLOYMENT「时钟」），这里不处理跳变。
  - 每 0.5 秒查询一次 ``/status``，并确认根组还在。发出的查询超过 2 秒没有回复才算离线：按"问了没回"
    判断，主机自己的线程偶尔卡住几秒（没有发出查询）不会被误判成合成器服务停了。连不上时什么都不发；重新连上（包括第一次
    连上和 scsynth 重启）后加载音色、建立根组，并报告"重新启动过"，由引擎重建混音结构并重新对账。
  - 用 ``/notify`` 订阅节点结束通知（``/n_end``），声部自然结束时通知引擎。
  - 各模式实例混音结构里的电平（``/sm_peak``）供控制台的每环电平和看板的输出电平使用。

节点树、总线和缓冲区的分配见 docs/implementation/SYNTH.md。
"""
from __future__ import annotations

import logging
import math
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Sequence

from pythonosc.osc_bundle_builder import IMMEDIATELY, OscBundleBuilder
from pythonosc.osc_message import OscMessage
from pythonosc.osc_message_builder import OscMessageBuilder

from ..timebase import system_time
from ..intent import Source
from .backend import BackendEvents
from .spatial import SpeakerGains

log = logging.getLogger("soundmat.scsynth")

ROOT_GROUP = 100
MASTER_GROUP = 101
FIRST_PRIVATE_BUS = 128        # 私有音频总线从这里开始（硬件输入输出不超过 128 个声道）
AUDIO_BUSES = 1024             # scsynth 默认的音频总线数（-a）
MAX_MIX_INPUTS = 12            # sm_mode 的输入数
STATUS_PERIOD = 0.5
OFFLINE_AFTER = 2.0
MAX_DGRAM = 8000
HEAD, TAIL = 0, 1


class Allocator:
    """连续区间的首次适应分配器（总线、缓冲区编号）。"""

    def __init__(self, start: int, end: int):
        self.free: list[tuple[int, int]] = [(start, end)]

    def alloc(self, n: int) -> int:
        for i, (a, b) in enumerate(self.free):
            if b - a >= n:
                self.free[i] = (a + n, b)
                return a
        raise RuntimeError("合成器服务的总线或缓冲区不够用")

    def release(self, start: int, n: int) -> None:
        self.free.append((start, start + n))
        self.free.sort()
        merged: list[tuple[int, int]] = []
        for a, b in self.free:
            if merged and merged[-1][1] == a:
                merged[-1] = (merged[-1][0], b)
            else:
                merged.append((a, b))
        self.free = merged


@dataclass
class Mix:
    group: int
    mode_node: int
    fx_node: int
    channels: int
    buses: dict[str, int]
    fx_bus: int
    fx_return: int
    allocations: list[tuple[int, int]] = field(default_factory=list)


def wall_time(at: float) -> float:
    """系统时间 → 墙钟时间（Unix 秒）。"""
    return time.time() + (at - system_time())


def _msg(address: str, *args) -> OscMessage:
    b = OscMessageBuilder(address)
    for a in args:
        if isinstance(a, bool):
            b.add_arg(int(a))
        elif isinstance(a, float):
            b.add_arg(a, "f")
        else:
            b.add_arg(a)
    return b.build()


def db(x: float) -> float:
    return 20 * math.log10(x) if x > 1e-6 else -120.0


class ScsynthCommands:
    """把声音引擎的抽象指令翻译成 scsynth 的 OSC 指令，并给节点、总线和缓冲区编号记账。

    指令只经两个出口交出，由子类实现：``send``（立即执行的单条指令）和 ``schedule``（在系统时间 ``at``
    执行的指令）；``flush`` 在一拍结束时调用。合成器服务的通知由子类转进来：音色加载好之后调用
    ``build_tree``，节点结束时调用 ``node_ended``；``poll`` 把积累的通知交给引擎。
    """

    records_audio = True

    def __init__(self, synthdefs: Path | None = None,
                 resolve_asset: Callable[[str], object | None] = lambda ref: None):
        self.synthdefs = Path(synthdefs) if synthdefs else None
        self.resolve_asset = resolve_asset
        self.online = False
        self.state = "offline"           # offline / loading / ready
        self._restarted = False
        self._ended: list[int] = []
        # 混音组、总输出、录音节点的编号从这里往下数，重连也不归零（见 _node）
        self._next_node = 2_000_000_000
        self._reset_state()

    def _reset_state(self) -> None:
        self.mixes: dict[str, Mix] = {}
        self.voices: dict[int, str] = {}
        self.buffers: dict[str, tuple[int, int]] = {}     # 引用 → (缓冲区编号, 声道数)
        self.bus_alloc = Allocator(FIRST_PRIVATE_BUS, AUDIO_BUSES)
        self.buf_alloc = Allocator(0, 1024)
        self.master_node: int | None = None
        self.master_channels = 0
        self.main_bus: int | None = None
        self.silent_bus: int | None = None
        self.trash_bus: int | None = None
        self.stem_buses: dict[str, int] = {}          # 全局分轨总线：总线名 → 编号
        self.recording: list[tuple[int, int]] = []     # 正在录制：(节点, 缓冲区)
        self._master_params: dict[str, float] = {}
        self._deferred: list[tuple[float, int, int]] = []

    # ── 出口（子类实现）─────────────────────────────────────────────────

    def send(self, msg: OscMessage) -> None:
        """立即执行的单条指令。"""
        raise NotImplementedError

    def schedule(self, at: float, msg: OscMessage) -> None:
        """在系统时间 ``at`` 执行的指令。"""
        raise NotImplementedError

    def flush(self) -> None:
        """一拍结束时调用：把暂存的定时指令发出去。"""

    def _node(self) -> int:
        """新的节点编号，永不重复使用。重连时节点树被清空，但已经发出、排在未来时刻的指令还在合成器
        服务的队列里，会在清空之后照常执行；如果新的混音组拿到和旧的相同的编号，那些指令建出的声音
        就落进新组、成了主机程序不知道的节点，没人释放（2026-10-18 在 Pi 3B 上留下了 7 个和声铺底，
        负载升到 80%）。编号不重复，旧指令指向的组已经不存在，合成器服务直接丢弃。"""
        self._next_node -= 1
        return self._next_node

    # ── 节点树与通知 ────────────────────────────────────────────────────

    def load_synthdefs(self) -> bool:
        """让合成器服务加载编译好的音色；找不到音色目录时记一条错误、返回 False。"""
        if self.synthdefs is not None and self.synthdefs.is_dir():
            self.send(_msg("/d_loadDir", str(self.synthdefs.resolve())))
            return True
        log.error("找不到编译好的音色：%s（在开发机上运行 scripts/compile_instruments.py）", self.synthdefs)
        return False

    def build_tree(self) -> None:
        """音色加载好之后：清空整棵节点树，建立根组和总输出组，开始接受指令。

        主机程序重启时 scsynth 照常运行，上一次留下的节点还在，所以先清空（scsynth 只为 SoundMat 服务）。
        """
        self._reset_state()
        self.send(_msg("/g_freeAll", 0))
        self.send(_msg("/g_new", ROOT_GROUP, HEAD, 0, MASTER_GROUP, TAIL, 0))
        self.state = "ready"
        self.online = True

    def node_ended(self, node: int) -> None:
        """合成器服务报告一个节点结束了（``/n_end``）；是声部的话，下一次 ``poll`` 时告诉引擎。"""
        if self.voices.pop(node, None) is not None:
            self._ended.append(node)

    def poll(self, now: float) -> BackendEvents:
        """释放到期的总线，交出积累的通知：结束了的声部，以及合成器服务是否重新启动过。"""
        for item in [d for d in self._deferred if d[0] <= now]:
            self._deferred.remove(item)
            self.bus_alloc.release(item[1], item[2])
        ev = BackendEvents(ended=self._ended, restarted=self._restarted)
        self._ended, self._restarted = [], False
        return ev

    # ── 总输出 ──────────────────────────────────────────────────────────

    def _ensure_master(self, channels: int, at: float) -> None:
        if self.master_node is not None and self.master_channels == channels:
            return
        if self.master_node is not None:
            self.stop_recording(at)
            self.schedule(at, _msg("/n_free", self.master_node))
            for b in [self.main_bus, self.silent_bus, self.trash_bus, *self.stem_buses.values()]:
                self._deferred.append((at + 1.0, b, self.master_channels))
            self.stem_buses = {}
        self.master_channels = channels
        self.main_bus = self.bus_alloc.alloc(channels)
        self.silent_bus = self.bus_alloc.alloc(channels)
        self.trash_bus = self.bus_alloc.alloc(channels)
        self.master_node = self._node()
        args = ["in", self.main_bus]
        for k, v in self._master_params.items():
            args += [k, float(v)]
        self.schedule(at, _msg("/s_new", f"sm_master_{channels}", self.master_node, HEAD, MASTER_GROUP, *args))

    def set_master(self, params: Mapping[str, float], at: float) -> None:
        self._master_params.update(params)
        if self.master_node is None:
            return
        args = []
        for k, v in params.items():
            args += [k, float(v)]
        self.schedule(at, _msg("/n_set", self.master_node, *args))

    def test_tone(self, channel: int, at: float) -> None:
        if self.master_channels:
            self.schedule(at, _msg("/s_new", f"sm_test_tone_{self.master_channels}", -1, TAIL, MASTER_GROUP,
                                   "channel", int(channel)))

    # ── 混音结构 ────────────────────────────────────────────────────────

    def create_mix(self, instance: str, buses: Sequence[str], channels: int, at: float,
                   fx: str | None = None) -> None:
        if self.state != "ready":
            return
        self._ensure_master(channels, at)
        allocs = []

        def bus() -> int:
            b = self.bus_alloc.alloc(channels)
            allocs.append((b, channels))
            return b

        names = list(buses)[:MAX_MIX_INPUTS]
        bus_map = {name: bus() for name in names}
        fx_bus, fx_return = bus(), bus()
        mix = Mix(group=self._node(), mode_node=self._node(), fx_node=self._node(), channels=channels,
                  buses=bus_map, fx_bus=fx_bus, fx_return=fx_return, allocations=allocs)
        self.mixes[instance] = mix
        self.schedule(at, _msg("/g_new", mix.group, TAIL, ROOT_GROUP))
        self.schedule(at, _msg("/s_new", f"{fx or 'sm_fx_freeverb'}_{channels}", mix.fx_node, TAIL, mix.group,
                               "in", fx_bus, "out", fx_return))
        args: list = ["out", self.main_bus, "fxIn", fx_return, "mixGain", 0.0, "stemFx", self._stem("fx", channels)]
        for i in range(MAX_MIX_INPUTS):
            used = i < len(names)
            args += [f"in{i}", bus_map[names[i]] if used else self.silent_bus,
                     f"stem{i}", self._stem(names[i], channels) if used else self.trash_bus]
        self.schedule(at, _msg("/s_new", f"sm_mode_{channels}", mix.mode_node, TAIL, mix.group, *args))

    def _stem(self, name: str, channels: int) -> int:
        if name not in self.stem_buses:
            self.stem_buses[name] = self.bus_alloc.alloc(channels)
        return self.stem_buses[name]

    def set_mix_gain(self, instance: str, gain: float, fade: float, at: float) -> None:
        mix = self.mixes.get(instance)
        if mix:
            self.schedule(at, _msg("/n_set", mix.mode_node, "mixFade", float(fade), "mixGain", float(gain)))

    def free_mix(self, instance: str, at: float) -> None:
        mix = self.mixes.pop(instance, None)
        if mix is None:
            return
        self.schedule(at, _msg("/n_free", mix.group))
        for node, inst in list(self.voices.items()):
            if inst == instance:
                del self.voices[node]
        for start, n in mix.allocations:
            self._deferred.append((at + 1.0, start, n))

    def set_globals(self, instance: str, params: Mapping[str, float], at: float) -> None:
        """``bus.<总线>`` 设置该总线的增益，``fx.<参数>`` 设置共用效果，其余交给模式总处理。"""
        mix = self.mixes.get(instance)
        if mix is None:
            return
        names = list(mix.buses)
        mode_args: list = []
        fx_args: list = []
        for k, v in params.items():
            if k.startswith("bus."):
                name = k[4:]
                if name in names:
                    mode_args += [f"gain{names.index(name)}", float(v)]
            elif k.startswith("fx."):
                fx_args += [k[3:], float(v)]
            else:
                mode_args += [k, float(v)]
        if mode_args:
            self.schedule(at, _msg("/n_set", mix.mode_node, *mode_args))
        if fx_args:
            self.schedule(at, _msg("/n_set", mix.fx_node, *fx_args))

    # ── 声部 ────────────────────────────────────────────────────────────

    def _gain_args(self, gains: SpeakerGains) -> list:
        args: list = []
        for prefix, values in (("g", gains.mono), ("gl", gains.left), ("gr", gains.right)):
            for i, v in enumerate(values):
                args += [f"{prefix}{i}", float(v)]
        return args

    def start_voice(self, node: int, instance: str, source: Source, bus: str,
                    params: Mapping[str, float], gains: SpeakerGains, fade_in: float,
                    at: float, oneshot: bool) -> None:
        mix = self.mixes.get(instance)
        if mix is None:
            return
        args: list = []
        if source.kind == "sample":
            loaded = self.buffers.get(source.name)
            if loaded is None:
                self._ended.append(node)      # 素材缺失：不发声，立即当作结束
                return
            bufnum, chans = loaded
            name = "sm_play_" + ("mono" if chans == 1 else "stereo") + ("_tune" if "semitones" in params else "")
            args += ["buf", bufnum, "loop", 0 if oneshot else 1]
        else:
            name = source.name
        out = mix.buses.get(bus)
        if out is None:
            out = next(iter(mix.buses.values()))
        args += ["out", out, "fx", mix.fx_bus]
        if not oneshot:
            args += ["atk", float(fade_in), "gate", 1]
        for k, v in params.items():
            args += [k, float(v)]
        args += self._gain_args(gains)
        self.voices[node] = instance
        self.schedule(at, _msg("/s_new", f"{name}_{mix.channels}", node, HEAD, mix.group, *args))

    def set_voice(self, node: int, params: Mapping[str, float], gains: SpeakerGains | None, at: float) -> None:
        if node not in self.voices:
            return
        args: list = []
        for k, v in params.items():
            args += [k, float(v)]
        if gains is not None:
            args += self._gain_args(gains)
        if args:
            self.schedule(at, _msg("/n_set", node, *args))

    def release_voice(self, node: int, fade_out: float, at: float) -> None:
        if node in self.voices:
            self.schedule(at, _msg("/n_set", node, "rel", float(fade_out), "gate", 0))

    def free_voice(self, node: int, at: float) -> None:
        if self.voices.pop(node, None) is not None:
            self.schedule(at, _msg("/n_free", node))

    # ── 素材 ────────────────────────────────────────────────────────────

    def load_asset(self, ref: str, at: float) -> None:
        if self.state != "ready" or ref in self.buffers:
            return
        info = self.resolve_asset(ref)
        if info is None:
            return
        bufnum = self.buf_alloc.alloc(1)
        self.buffers[ref] = (bufnum, int(getattr(info, "channels", 1)))
        self.send(_msg("/b_allocRead", bufnum, str(getattr(info, "path"))))

    def free_asset(self, ref: str, at: float) -> None:
        loaded = self.buffers.pop(ref, None)
        if loaded is not None:
            self.schedule(at + 1.0, _msg("/b_free", loaded[0]))
            self.buf_alloc.release(loaded[0], 1)

    # ── 录制 ────────────────────────────────────────────────────────────

    def recordable_stems(self) -> list[str]:
        return list(self.stem_buses)

    def start_recording(self, files: Mapping[str, str], at: float) -> list[str]:
        """``files``：``"master"`` 或分轨总线名 → 文件路径。返回实际开始录制的项。"""
        if self.state != "ready" or self.master_node is None or self.recording:
            return []
        n = self.master_channels
        started = []
        for name, path in files.items():
            src = 0 if name == "master" else self.stem_buses.get(name)
            if src is None:
                continue
            buf = self.buf_alloc.alloc(1)
            node = self._node()
            # 异步命令按顺序执行：先分配、再打开文件；录制节点在稍后的时刻开始
            self.send(_msg("/b_alloc", buf, 65536, n))
            # 总输出经过限幅，用 24 位；分轨在总处理之前，可能超过 0 dBFS，用 32 位浮点避免削波
            fmt = "int24" if name == "master" else "float"
            self.send(_msg("/b_write", buf, str(path), "wav", fmt, 0, 0, 1))
            self.schedule(at, _msg("/s_new", f"sm_rec_{n}", node, TAIL, MASTER_GROUP, "buf", buf, "in", src))
            self.recording.append((node, buf))
            started.append(name)
        return started

    def stop_recording(self, at: float) -> None:
        for node, buf in self.recording:
            self.schedule(at, _msg("/n_free", node))
            self.schedule(at, _msg("/b_close", buf))
            self.schedule(at, _msg("/b_free", buf))
            self.buf_alloc.release(buf, 1)
        self.recording = []

    def recording_active(self) -> bool:
        return bool(self.recording)

    def slate(self, at: float) -> None:
        """打板提示音：直接写到硬件输出，加在 MASTER_GROUP 末尾。与录音同一时刻开始时，先调用
        ``start_recording`` 再调用这里，它就排在录音节点之后，只在现场响、不进录音。"""
        if self.master_node is not None:
            self.schedule(at, _msg("/s_new", f"sm_slate_{self.master_channels}", -1, TAIL, MASTER_GROUP,
                                   "out", 0))


class ScsynthBackend(ScsynthCommands):
    """实时连接：经 UDP 把指令发给运行中的合成器服务，查询它的状态、接收它的通知（见模块说明）。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 57110,
                 synthdefs: Path | None = None,
                 resolve_asset: Callable[[str], object | None] = lambda ref: None):
        super().__init__(synthdefs, resolve_asset)
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1" if host in ("127.0.0.1", "localhost") else "0.0.0.0", 0))
        self.sock.setblocking(False)
        self.info: dict = {}
        self.defs_loaded = False
        self.ever_online = False
        self._last_reply = -1e9
        self._unanswered_since: float | None = None    # 最早一次还没收到回复的 /status 查询的时刻
        self._next_status = 0.0
        self._pending: dict[float, list[OscMessage]] = {}
        self._lock = threading.Lock()
        self._levels: dict[tuple[int, int], tuple[float, list[float]]] = {}

    # ── 发送 ────────────────────────────────────────────────────────────

    def send(self, msg: OscMessage) -> None:
        try:
            self.sock.sendto(msg.dgram, self.addr)
        except OSError as e:
            log.debug("发送失败：%s", e)

    def schedule(self, at: float, msg: OscMessage) -> None:
        if self.state != "ready":
            return
        self._pending.setdefault(round(at, 6), []).append(msg)

    def flush(self) -> None:
        pending, self._pending = self._pending, {}
        now = system_time()
        for at in sorted(pending):
            stamp = IMMEDIATELY if at <= now + 0.001 else wall_time(at)
            msgs = pending[at]
            chunk: list[OscMessage] = []
            size = 0
            for m in msgs + [None]:
                if m is None or (chunk and size + m.size > MAX_DGRAM):
                    b = OscBundleBuilder(stamp)
                    for c in chunk:
                        b.add_content(c)
                    try:
                        self.sock.sendto(b.build().dgram, self.addr)
                    except OSError as e:
                        log.debug("发送失败：%s", e)
                    chunk, size = [], 0
                if m is not None:
                    chunk.append(m)
                    size += m.size + 4

    # ── 连接与通知 ──────────────────────────────────────────────────────

    def poll(self, now: float) -> BackendEvents:
        self._receive(now)
        if now >= self._next_status:
            self._next_status = now + STATUS_PERIOD
            self.send(_msg("/status"))
            if self._unanswered_since is None:
                self._unanswered_since = now
            if self.state == "ready":
                self.send(_msg("/n_query", ROOT_GROUP))
        waiting = self._unanswered_since
        if self.state != "offline" and waiting is not None and now - waiting > OFFLINE_AFTER:
            log.warning("合成器服务没有响应")
            self._go_offline()
        return super().poll(now)

    def _go_offline(self) -> None:
        self.state = "offline"
        self.online = False
        self._pending.clear()
        self._reset_state()

    def _receive(self, now: float) -> None:
        while True:
            try:
                data, _ = self.sock.recvfrom(65536)
            except (BlockingIOError, InterruptedError):
                return
            except OSError:
                return
            try:
                msg = OscMessage(data)
            except Exception:
                continue
            self._handle(msg.address, list(msg.params), now)

    def _handle(self, addr: str, args: list, now: float) -> None:
        if addr == "/status.reply":
            self._last_reply = now
            self._unanswered_since = None
            keys = ("ugens", "synths", "groups", "defs", "avgCPU", "peakCPU", "nominalSampleRate", "actualSampleRate")
            self.info = dict(zip(keys, args[1:9]))
            if self.state == "offline":
                self._begin_connect()
        elif addr == "/done" and args and args[0] == "/d_loadDir":
            self.defs_loaded = True
            if self.state == "loading":
                self._setup()
        elif addr == "/fail":
            if args and args[0] == "/n_query" and self.state == "ready":
                log.warning("合成器服务重新启动过")
                self._reset_state()
                self._begin_connect()
            elif args and args[0] == "/d_loadDir":
                log.error("无法加载音色：%s", args[1:])
                self.defs_loaded = False
                if self.state == "loading":
                    self._setup()
            else:
                log.debug("scsynth：%s", args)
        elif addr == "/n_end" and args:
            self.node_ended(int(args[0]))
        elif addr == "/sm_peak" and len(args) >= 2:
            node, rid = int(args[0]), int(args[1])
            peaks = [float(x) for x in args[2::2]]
            with self._lock:
                self._levels[(node, rid)] = (now, peaks)

    def _begin_connect(self) -> None:
        self.state = "loading"
        self.defs_loaded = False
        self.send(_msg("/notify", 1))
        if not self.load_synthdefs():
            self._setup()

    def _setup(self) -> None:
        """第一次连上或重新启动后：建立节点树，报告"重新启动过"让引擎重建。"""
        self.build_tree()
        self.ever_online = True
        self._restarted = True
        log.info("合成器服务已连接")

    # ── 监测 ────────────────────────────────────────────────────────────

    def status(self) -> dict:
        return {"online": self.online, "everOnline": self.ever_online, "state": self.state,
                "synthdefsLoaded": self.defs_loaded, **self.info}

    def levels(self, instance: str | None, meters: Sequence[Sequence[str]], now: float | None = None) -> dict | None:
        """总输出各声道的峰值电平，以及每根电平条的峰值电平（dBFS）：取这根条的各条总线、所有声道的最大值。

        ``meters`` 是每根条对应的总线名；只看 ``instance`` 这个模式实例（切换期间是新实例）。
        超过 1 秒没有更新的值不算。
        """
        now = system_time() if now is None else now
        with self._lock:
            fresh = {k: v[1] for k, v in self._levels.items() if now - v[0] < 1.0}
        if self.master_node is None:
            return None
        output = [db(p) for p in fresh.get((self.master_node, 100), [])]
        mix = self.mixes.get(instance) if instance else None
        names = list(mix.buses) if mix else []
        values = []
        for buses in meters:
            peak = 0.0
            for b in buses:
                if mix and b in names:
                    peak = max([peak, *fresh.get((mix.mode_node, names.index(b)), [])])
            values.append(round(db(peak), 1))
        return {"output": [round(x, 1) for x in output], "meters": values}
