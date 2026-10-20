#!/usr/bin/env python3
"""离线渲染一份编排：uv run python scripts/render.py <编排> <时间表.json> <输出.wav> [--stats]

用主机程序真实的声音化（感知、模式、声音引擎、素材库）和编译好的音色，按模拟时间以 ``sound.tick_hz``
一拍一拍地演奏一张石头时间表，把合成器服务本该收到的全部指令记成 scsynth 的非实时乐谱（时刻 = 模拟时间），
再用 ``scsynth -N`` 渲染成 WAV。不连合成器服务，也不出声。用来对比音色、调编排电平、按渲染耗时估算负载，
不必每次都上真机（docs/implementation/SYNTH.md「离线渲染」）。

时间表（JSON；时刻是秒，从渲染开始算；环号是主机程序的，由内到外 0–7，slot 是环内序号；
scripts/scenes/ 里有几张参考的）：

    {"duration": 150,
     "stones": [{"ring": 0, "slot": 3, "on": 2.0, "off": null}, ...],
     "control": [{"on": 2.0, "off": null, "pressure": 400}]}

石头按虚拟垫子的压力放下（off 为 null 表示一直放着），经过真实的去抖。``control`` 可省略：控制区
（例如 Jam 的内两环）上额外的压力总和，和编排、配置里的压力一样用 ADC 原始读数（满量程 4095），
平均分到各控制区；同时有几段时相加，放在控制区上的石头照常计入。

输出 scsynth 的报错、渲染用时（扣掉启动和加载，折算负载用）、同时存在的声部最多几个、引擎计数；
``--stats`` 另外打印 BS.1770 响度、峰值和每 10 秒的平均电平。
"""
from __future__ import annotations

import argparse
import dataclasses
import heapq
import itertools
import json
import logging
import math
import operator
import re
import struct
import subprocess
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

import numpy as np
import soundfile
from pythonosc.osc_message import OscMessage
from pythonosc.osc_message_builder import OscMessageBuilder

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from soundmat.clock import Beat  # noqa: E402
from soundmat.config import Config, MatConfig, load_config  # noqa: E402
from soundmat.exchange import Latest  # noqa: E402
from soundmat.intent import LightIntent, Source  # noqa: E402
from soundmat.monitor.log import EventLog  # noqa: E402
from soundmat.perception import Perception  # noqa: E402
from soundmat.perception.model import PressureMap  # noqa: E402
from soundmat.perception.virtual import STONE_PRESSURE  # noqa: E402
from soundmat.perception.zones import NUM_RINGS, NUM_ZONES, zone, zones_in_ring  # noqa: E402
from soundmat.sonification import Sonification  # noqa: E402
from soundmat.sonification.arrangements import ARRANGEMENTS_DIR, load_arrangement  # noqa: E402
from soundmat.sonification.mode import Arrangement, LoadError, ModeContext  # noqa: E402
from soundmat.sound.assets import AssetLibrary  # noqa: E402
from soundmat.sound.backend import BackendEvents  # noqa: E402
from soundmat.sound.engine import SoundEngine  # noqa: E402
from soundmat.sound.scsynth import MAX_DGRAM, ScsynthCommands  # noqa: E402
from soundmat.sound.scsynth_process import find_scsynth  # noqa: E402
from soundmat.sound.spatial import PRESETS, SpeakerGains  # noqa: E402
from soundmat.store import Store  # noqa: E402
from soundmat.store.settings import default_sound_library, defaults  # noqa: E402
from soundmat.supervisor import MODES  # noqa: E402

LAYOUTS = {2: "stereo", 4: "quad", 8: "octo"}
DEFAULT_ONESHOT = 2.0       # 秒：算不出长度的单次声音按这么长估算（与不发声的 RecordingBackend 相同）
NO_BUDGET = 1_000_000       # 不按声部预算让位时的"预算"


# ── 声部的长度 ──────────────────────────────────────────────────────────────
#
# 离线渲染时合成器服务不回报 /n_end，声部什么时候结束要自己算，否则引擎一直以为它们还在响，声部表越积越多。
# 音色的长度直接从编译好的 SynthDef 里算：找出会释放整个声部的 UGen（doneAction 2 的 EnvGen、Line、XLine），
# 用这个声部实际的参数求出包络的总时长，取最早结束的那个。音色改了长度，这里自动跟着变。


@dataclass(frozen=True)
class UGen:
    name: str
    inputs: tuple[tuple[int, int], ...]     # (UGen 序号, 输出序号)；UGen 序号为 -1 时第二项是常数序号
    special: int


@dataclass(frozen=True)
class SynthDefGraph:
    """编译好的 SynthDef（SCgf 第 2 版）中估算长度用得到的部分。"""
    name: str
    constants: tuple[float, ...]
    defaults: tuple[float, ...]             # 各参数的默认值
    params: dict[str, int]                  # 参数名 → 序号
    ugens: tuple[UGen, ...]


def read_synthdef(path: Path) -> SynthDefGraph:
    """读取 .scsyndef 文件里的第一个 SynthDef（每个文件只有一个）。"""
    data = path.read_bytes()
    pos = 0

    def take(fmt: str) -> tuple:
        nonlocal pos
        values = struct.unpack_from(">" + fmt, data, pos)
        pos += struct.calcsize(">" + fmt)
        return values

    def text() -> str:
        nonlocal pos
        n = data[pos]
        pos += 1 + n
        return data[pos - n:pos].decode("latin-1")

    magic, version, _ = take("4sih")
    if magic != b"SCgf" or version != 2:
        raise ValueError(f"{path.name} 不是第 2 版的 SynthDef 文件")
    name = text()
    constants = take(f"{take('i')[0]}f")
    defaults_ = take(f"{take('i')[0]}f")
    params = {}
    for _ in range(take("i")[0]):
        key = text()
        params[key] = take("i")[0]
    ugens = []
    for _ in range(take("i")[0]):
        cls = text()
        _rate, n_in, n_out, special = take("biih")
        inputs = tuple(take("ii") for _ in range(n_in))
        take(f"{n_out}b")
        ugens.append(UGen(cls, inputs, special))
    return SynthDefGraph(name, constants, defaults_, params, tuple(ugens))


CONTROLS = {"Control", "LagControl", "TrigControl", "AudioControl"}
# BinaryOpUGen / UnaryOpUGen 的运算序号（SuperCollider 服务器的运算表）
BINARY: dict[int, Callable[[float, float], float]] = {
    0: operator.add, 1: operator.sub, 2: operator.mul, 4: lambda a, b: a / b if b else 0.0,
    12: min, 13: max,
}
UNARY: dict[int, Callable[[float], float]] = {0: operator.neg, 5: abs}
SELF_FREEING_OTHER = {"FreeSelfWhenDone", "DetectSilence", "FreeSelf", "PauseSelfWhenDone", "PauseSelf"}
NO_NODE = -99               # 包络没有释放点、循环点时的值


def synth_lifetime(graph: SynthDefGraph, params: Mapping[str, float]) -> float | None:
    """用这些参数开始的声部多久之后释放自己（秒）：不会自己结束时为 inf（要等引擎让它淡出），
    结束的条件算不出来时（例如取决于随机数、素材长度）为 None。"""
    values = list(graph.defaults)
    for key, v in params.items():
        if key in graph.params:
            values[graph.params[key]] = float(v)

    def value(ref: tuple[int, int]) -> float | None:
        index, out = ref
        if index < 0:
            return graph.constants[out]
        u = graph.ugens[index]
        if u.name in CONTROLS:
            return values[u.special + out]
        if u.name == "Select":
            which = value(u.inputs[0])
            if which is None:
                return None
            return value(u.inputs[min(max(int(which) + 1, 1), len(u.inputs) - 1)])
        args = [value(r) for r in u.inputs]
        if any(a is None for a in args):
            return None
        if u.name == "BinaryOpUGen" and u.special in BINARY:
            return BINARY[u.special](args[0], args[1])
        if u.name == "UnaryOpUGen" and u.special in UNARY:
            return UNARY[u.special](args[0])
        if u.name == "MulAdd":
            return args[0] * args[1] + args[2]
        if u.name in ("Sum3", "Sum4"):
            return sum(args)
        return None

    ends: list[float | None] = []
    for u in graph.ugens:
        if u.name in ("Line", "XLine"):              # start, end, dur, doneAction
            if value(u.inputs[3]) == 2:
                ends.append(value(u.inputs[2]))
        elif u.name == "EnvGen":                      # gate, levelScale, levelBias, timeScale, doneAction, 包络……
            if value(u.inputs[4]) != 2:
                continue
            env = u.inputs[5:]                        # 起始电平, 段数, 释放点, 循环点, (电平, 时长, 形状, 曲率) × 段数
            stages, release, loop = value(env[1]), value(env[2]), value(env[3])
            if stages is None or release is None or loop is None:
                ends.append(None)
            elif loop != NO_NODE:
                ends.append(math.inf)
            elif release != NO_NODE:                  # 门开着就停在释放点，等门关上
                gate = value(u.inputs[0])
                ends.append(math.inf if gate is not None and gate > 0 else None)
            else:
                times = [value(env[5 + 4 * k]) for k in range(int(stages))]
                scale = value(u.inputs[3])
                ends.append(None if scale is None or None in times else scale * sum(times))
        elif u.name in SELF_FREEING_OTHER:
            ends.append(None)
    if None in ends:
        return None
    return min(ends, default=math.inf)


class Lifetimes:
    """估算每个声部在合成器服务里活多久，供乐谱后端模拟 /n_end。

    - 音色：``synth_lifetime``，用声部实际收到的参数；
    - 单次播放的素材（loop 0）：放完为止，时长 = 帧数 / 采样率 / 速度（rateVar 取最慢的一端）；循环的素材不会自己结束；
    - 算不出长度的单次声音按 ``DEFAULT_ONESHOT`` 估算，记在 ``guessed``；不会自己结束的单次声音记在 ``endless``
      （在装置上它会一直占着声部，是音色或编排的错误）。
    """

    def __init__(self, synthdefs: Path, resolve_asset: Callable[[str], object | None]):
        self.dir = Path(synthdefs)
        self.resolve_asset = resolve_asset
        self.guessed: set[str] = set()
        self.endless: set[str] = set()
        self._graphs: dict[str, SynthDefGraph | None] = {}

    def graph(self, name: str) -> SynthDefGraph | None:
        if name not in self._graphs:
            try:
                self._graphs[name] = read_synthdef(self.dir / f"{name}.scsyndef")
            except (OSError, ValueError, struct.error):
                self._graphs[name] = None
        return self._graphs[name]

    def of(self, source: Source, params: Mapping[str, float], channels: int, oneshot: bool) -> float:
        """声部开始之后多久结束（秒）；``inf`` 表示要等引擎让它淡出。``params`` 是发给音色的全部参数。"""
        if source.kind == "sample":
            info = self.resolve_asset(source.name)
            if not oneshot or info is None:
                return math.inf
            rate = abs(params.get("rate", 1.0)) * 2 ** (-abs(params.get("rateVar", 0.0)) / 12)
            frames = max(0.0, getattr(info, "frames") - params.get("startPos", 0.0))
            return frames / getattr(info, "sample_rate") / max(rate, 1e-6)
        graph = self.graph(f"{source.name}_{channels}")
        life = synth_lifetime(graph, params) if graph is not None else None
        if not oneshot:
            return math.inf if life is None else life
        if life is None:
            self.guessed.add(source.name)
            return DEFAULT_ONESHOT
        if life == math.inf:
            self.endless.add(source.name)
        return life


# ── 乐谱 ────────────────────────────────────────────────────────────────────


class ScoreBackend(ScsynthCommands):
    """合成器服务的离线替身：和实时连接用同一套翻译（``ScsynthCommands``），把指令记成乐谱。

    时刻是模拟时间 ``now``，由驱动的一方在每拍开始时设置。立即执行的指令记在当前时刻；定时指令先暂存，
    ``flush`` 时（一拍结束）再记进乐谱，同一时刻的先后与实时连接发到合成器服务的顺序一致。
    节点结束按 ``Lifetimes`` 模拟：单次声音和有固定长度的声部按算出的长度结束，淡出的声部在淡出时长
    之后结束；被强制释放的声部立即从声部表里去掉，不再通知。
    """

    def __init__(self, synthdefs: Path, resolve_asset: Callable[[str], object | None] = lambda ref: None):
        super().__init__(synthdefs, resolve_asset)
        self.now = 0.0
        self.score: list[tuple[float, OscMessage]] = []
        self.lifetimes = Lifetimes(synthdefs, resolve_asset)
        self._pending: list[tuple[float, OscMessage]] = []
        self._ends: list[tuple[float, int]] = []
        if not self.load_synthdefs():
            raise FileNotFoundError(f"找不到编译好的音色：{synthdefs}（先运行 scripts/compile_instruments.py）")
        self.build_tree()

    def send(self, msg: OscMessage) -> None:
        self.score.append((self.now, msg))

    def schedule(self, at: float, msg: OscMessage) -> None:
        self._pending.append((max(at, self.now), msg))

    def flush(self) -> None:
        self.score += self._pending
        self._pending = []

    def start_voice(self, node: int, instance: str, source: Source, bus: str,
                    params: Mapping[str, float], gains: SpeakerGains, fade_in: float,
                    at: float, oneshot: bool) -> None:
        super().start_voice(node, instance, source, bus, params, gains, fade_in, at, oneshot)
        mix = self.mixes.get(instance)
        if mix is None or node not in self.voices:        # 没有发出（没有混音结构，或素材缺失）
            return
        sent = dict(params) if oneshot else {**params, "atk": fade_in, "gate": 1.0}
        life = self.lifetimes.of(source, sent, mix.channels, oneshot)
        if life != math.inf:
            heapq.heappush(self._ends, (max(at, self.now) + life, node))

    def release_voice(self, node: int, fade_out: float, at: float) -> None:
        if node in self.voices:
            heapq.heappush(self._ends, (max(at, self.now) + fade_out, node))
        super().release_voice(node, fade_out, at)

    def poll(self, now: float) -> BackendEvents:
        while self._ends and self._ends[0][0] <= now:
            self.node_ended(heapq.heappop(self._ends)[1])
        return super().poll(now)

    def status(self) -> dict | None:
        return None

    def levels(self, instance, meters, now=None) -> dict | None:
        return None

    def report(self, node, now=None):
        return None             # 非实时渲染时音色送回的数值收不到


def _timetag(t: float) -> bytes:
    """非实时乐谱的时间标签：从乐谱开头算起的秒数，32.32 定点（不加 NTP 纪元的偏移）。"""
    seconds = int(t)
    return struct.pack(">II", seconds, min(int((t - seconds) * 2**32), 2**32 - 1))


def _bundle(t: float, msgs: list[OscMessage]) -> bytes:
    body = b"#bundle\x00" + _timetag(t) + b"".join(struct.pack(">i", m.size) + m.dgram for m in msgs)
    return struct.pack(">i", len(body)) + body


def _end_marker() -> OscMessage:
    b = OscMessageBuilder("/c_set")
    b.add_arg(0)
    b.add_arg(0)
    return b.build()


def write_score(score: list[tuple[float, OscMessage]], path: Path, duration: float) -> int:
    """把乐谱写成 scsynth 非实时渲染读的文件，返回写入的指令数。

    文件是一串 bundle，每个前面加 4 字节的长度（大端）。按时刻排序，同一时刻的指令放进一个 bundle
    （超过 8 KB 拆成几个），保持记下的先后。渲染到最后一个 bundle 的时刻为止，所以最后在 ``duration``
    放一条无关紧要的 ``/c_set``；之后的指令丢掉。
    """
    entries = sorted(((round(t, 6), i, m) for i, (t, m) in enumerate(score) if t < duration),
                     key=lambda e: (e[0], e[1]))
    out = bytearray()
    count = 0
    for t, group in itertools.groupby(entries, key=lambda e: e[0]):
        chunk: list[OscMessage] = []
        size = 0
        for _, _, m in group:
            if chunk and size + m.size > MAX_DGRAM:
                out += _bundle(t, chunk)
                chunk, size = [], 0
            chunk.append(m)
            size += m.size + 4
            count += 1
        out += _bundle(t, chunk)
    out += _bundle(duration, [_end_marker()])
    Path(path).write_bytes(bytes(out))
    return count


# ── 时间表与模拟 ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Stone:
    zone: int               # 区域全局序号
    on: float
    off: float | None


@dataclass(frozen=True)
class Press:
    on: float
    off: float | None
    pressure: float         # ADC 原始读数的总和


@dataclass(frozen=True)
class Scenario:
    duration: float
    stones: tuple[Stone, ...] = ()
    control: tuple[Press, ...] = ()

    @staticmethod
    def from_json(data: dict) -> "Scenario":
        def number(x, what: str) -> float:
            if isinstance(x, bool) or not isinstance(x, (int, float)):
                raise ValueError(f"{what} 应是数值")
            return float(x)

        def span(item: dict, what: str) -> tuple[float, float | None]:
            on = number(item.get("on"), f"{what}的 on")
            off = item.get("off")
            off = None if off is None else number(off, f"{what}的 off")
            if on < 0 or (off is not None and off <= on):
                raise ValueError(f"{what}：应满足 0 ≤ on < off")
            return on, off

        duration = number(data.get("duration"), "duration")
        if duration <= 0:
            raise ValueError("duration 应大于 0")
        stones = []
        for k, s in enumerate(data.get("stones", [])):
            what = f"第 {k + 1} 颗石头"
            ring, slot = s.get("ring"), s.get("slot")
            if not isinstance(ring, int) or not 0 <= ring < NUM_RINGS:
                raise ValueError(f"{what}：ring 应是 0–{NUM_RINGS - 1}")
            if not isinstance(slot, int) or not 0 <= slot < zones_in_ring(ring):
                raise ValueError(f"{what}：第 {ring} 环的 slot 应是 0–{zones_in_ring(ring) - 1}")
            stones.append(Stone(zone(ring, slot).index, *span(s, what)))
        control = []
        for k, c in enumerate(data.get("control", [])):
            what = f"第 {k + 1} 段控制区压力"
            pressure = number(c.get("pressure"), f"{what}的 pressure")
            if 0 < pressure < 1:          # ADC 读数是整数，这么小的值多半是按归一化压力写的
                full = MatConfig().full_scale
                raise ValueError(f"{what}：pressure 用 ADC 原始读数之和（满量程 {full}，和编排一样），"
                                 f"{pressure:g} 像是归一化的压力，应写 {pressure * full:.0f}")
            control.append(Press(*span(c, what), pressure))
        return Scenario(duration, tuple(stones), tuple(control))

    @staticmethod
    def load(path: Path) -> "Scenario":
        try:
            data = json.loads(Path(path).read_text())
        except FileNotFoundError as e:
            raise FileNotFoundError(f"找不到时间表：{path}") from e
        except json.JSONDecodeError as e:
            raise ValueError(f"{Path(path).name} 不是有效的 JSON：{e}") from e
        return Scenario.from_json(data)

    def pressure(self, t: float, seq: int, control_zones: frozenset[int], mat: MatConfig) -> PressureMap:
        """``t`` 时刻的压力图：石头按虚拟垫子的压力，控制区的额外压力平均分到各控制区。"""
        def active(on: float, off: float | None) -> bool:
            return on <= t and (off is None or t < off)

        values = np.zeros(NUM_ZONES, dtype=np.float32)
        values[[s.zone for s in self.stones if active(s.on, s.off)]] = STONE_PRESSURE
        extra = sum(p.pressure for p in self.control if active(p.on, p.off))
        if extra and control_zones:
            zones = sorted(control_zones)
            values[zones] += mat.normalize(extra) / len(zones)
        return PressureMap(t, seq, values)


@dataclass
class Simulation:
    arrangement: Arrangement
    duration: float
    score: list[tuple[float, OscMessage]]
    real_budget: bool                       # 是否按配置的声部预算让位和放弃
    budget: tuple[int, dict[str, int]]      # 配置的声部预算：总数、各类别
    peak_voices: int                        # 同时存在的声部最多几个（引擎的声部表，含淡出中的）
    peak_categories: dict[str, int]         # 按声部类别
    counters: dict[str, int]                # 引擎计数：让位、因预算放弃、迟到、重复、重启
    missing: list[str]                      # 缺少的素材
    log: list[dict]                         # 运行中记下的警告和错误
    guessed: set[str]                       # 按默认长度估算的单次声音音色
    endless: set[str]                       # 不会自己结束的单次声音音色


def simulate(arrangement: Arrangement, scenario: Scenario, *, config: Config | None = None,
             channels: int = 2, volume: float | None = None, seed: int = 1, real_budget: bool = False,
             sound_dir: Path | None = None, synthdefs: Path | None = None) -> Simulation:
    """按模拟时间演奏时间表，返回乐谱和运行中的统计。组装方式与运行管理相同，只是不启动任何线程：
    每拍先把这一刻的压力图交给感知，再调用声音化的 ``on_beat``。"""
    cfg = config or load_config()
    sound = cfg.sound
    if not real_budget:
        sound = dataclasses.replace(sound, voice_budget_total=NO_BUDGET, voice_budget_categories={})
    if volume is None:
        volume = defaults(Path())["sound"]["volume"]
    backend = ScoreBackend(synthdefs or cfg.synth.synthdefs_path, resolve_asset=lambda ref: library.info(ref))
    library = AssetLibrary(Path(sound_dir or default_sound_library()).resolve(), sound.asset_memory_mb, backend)
    engine = SoundEngine(backend, sound, PRESETS[LAYOUTS[channels]])
    engine.on_rebuild.append(library.reload_all)
    store = Store()
    events = EventLog(store)
    perception = Perception(cfg.mat, source="virtual")
    sonification = Sonification(
        engine, library, perception, store, events, Latest(LightIntent()), modes=MODES,
        ctx=ModeContext(led_count=cfg.light.led_count, seed=seed, heard_after=sound.schedule_ahead))
    sonification.run_in_beat(lambda now: engine.set_master({"volume": float(volume)}, now))
    sonification.play(arrangement)

    period = 1.0 / sound.tick_hz
    peak = 0
    categories: Counter[str] = Counter()
    for i in range(math.ceil(scenario.duration * sound.tick_hz)):
        t = i * period
        backend.now = t
        active = sonification.active
        perception.feed(scenario.pressure(t, i, active.plan.control_zones if active else frozenset(), cfg.mat))
        sonification.on_beat(Beat(i, t, period))
        if sonification.active is None:       # 第一拍就该开始演奏；没开始是因为素材超出内存预算之类
            errors = [x["text"] for x in store.get("status.log", []) if x["level"] == "error"]
            raise LoadError(errors[0] if errors else f"{arrangement.title} 没有开始演奏")
        peak = max(peak, len(engine.voices))
        categories |= Counter(r.category for r in engine.voices.values() if r.category)

    return Simulation(
        arrangement=arrangement, duration=scenario.duration, score=backend.score, real_budget=real_budget,
        budget=(cfg.sound.voice_budget_total, dict(cfg.sound.voice_budget_categories)),
        peak_voices=peak, peak_categories=dict(categories), counters=engine.stats.to_json(),
        missing=list(store.get("status.assets.missing", [])),
        log=[x for x in reversed(store.get("status.log", [])) if x["level"] != "info"],
        guessed=backend.lifetimes.guessed, endless=backend.lifetimes.endless,
    )


# ── 渲染 ────────────────────────────────────────────────────────────────────

ERROR_MARKS = ("fail", "error", "exception", "not found", "not installed")
# 发给已经结束的节点的指令：引擎让一个按时刻开始的声部让位时，释放也按时刻排在提前量之后，
# 这期间声部可能已经自然结束了。装置上一样，合成器服务报一句"找不到节点"后忽略，无害。
ENDED_NODE = re.compile(r"/n_(free|set) Node -?\d+ not found")
LOADS = ("/d_loadDir", "/b_allocRead")


@dataclass
class Render:
    ok: bool                # 文件写出来了
    returncode: int
    seconds: float          # 渲染用时（包括 scsynth 启动、加载音色和素材）
    errors: list[str]       # scsynth 报的错
    output: str
    ended_nodes: int = 0    # 发给已经结束的节点的指令（无害，见 ENDED_NODE）
    load_seconds: float = 0.0   # 其中启动和加载的用时

    def cpu(self, duration: float) -> float:
        """合成本身的用时占音频时长的比例：合成器服务在装置上的 CPU 负载的参考。"""
        return max(0.0, self.seconds - self.load_seconds) / duration


def render(score: Path, out: Path, channels: int, sample_rate: int = 48000, scsynth: str | None = None) -> Render:
    """``scsynth -N`` 把乐谱渲染成 WAV（32 位浮点）。

    macOS 上 SC 3.14 的 scsynth 写完文件后会以 SIGSEGV 退出（返回 -11），文件是完整的，所以按"文件
    写出来了"判断成败，不看返回值；为此先删掉同名的旧文件。
    """
    binary = scsynth or find_scsynth()
    if binary is None:
        raise FileNotFoundError("找不到 scsynth（安装 SuperCollider，或用环境变量 SOUNDMAT_SCSYNTH 指定）")
    out = Path(out)
    out.unlink(missing_ok=True)
    start = time.monotonic()
    proc = subprocess.run([binary, "-N", str(score), "_", str(out), str(sample_rate), "WAV", "float",
                           "-o", str(channels), "-i", "0"], capture_output=True, text=True)
    seconds = time.monotonic() - start
    output = proc.stdout + proc.stderr
    marked = [line.strip() for line in output.splitlines() if any(k in line.lower() for k in ERROR_MARKS)]
    errors = [line for line in marked if not ENDED_NODE.search(line)]
    return Render(out.exists() and out.stat().st_size > 0, proc.returncode, seconds, errors, output,
                  ended_nodes=len(marked) - len(errors))


def render_simulation(sim: Simulation, out: Path, channels: int, sample_rate: int = 48000,
                      score: Path | None = None, scsynth: str | None = None) -> tuple[int, Render]:
    """写出乐谱并渲染，返回 (指令数, 渲染结果)。再单独渲染一份只有加载（音色、素材）的乐谱，
    量出启动和加载的用时：京都岚山光解码素材就要零点几秒，不扣掉的话短的场景负载会估高很多。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = score or Path(tmp) / "score.osc"
        count = write_score(sim.score, path, sim.duration)
        result = render(path, out, channels, sample_rate, scsynth)
        write_score([(t, m) for t, m in sim.score if m.address in LOADS], Path(tmp) / "load.osc", 0.01)
        result.load_seconds = render(Path(tmp) / "load.osc", Path(tmp) / "load.wav", channels, sample_rate,
                                     scsynth).seconds
    return count, result


# ── 响度与电平 ──────────────────────────────────────────────────────────────


def _k_weighting(sample_rate: int) -> list[tuple[list[float], list[float]]]:
    """BS.1770 的 K 计权：高架滤波器（+4 dB）和 38 Hz 高通，按采样率算出双二阶系数（同 libebur128）。"""
    f0, gain, q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    k = math.tan(math.pi * f0 / sample_rate)
    vh = 10 ** (gain / 20)
    vb = vh ** 0.4996667741545416
    a0 = 1 + k / q + k * k
    shelf = ([(vh + vb * k / q + k * k) / a0, 2 * (k * k - vh) / a0, (vh - vb * k / q + k * k) / a0],
             [1.0, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0])
    f0, q = 38.13547087602444, 0.5003270373238773
    k = math.tan(math.pi * f0 / sample_rate)
    a0 = 1 + k / q + k * k
    highpass = ([1.0, -2.0, 1.0], [1.0, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0])
    return [shelf, highpass]


def _filtered(x: np.ndarray, sample_rate: int) -> np.ndarray:
    """K 计权后的一个声道。用 FFT 乘以滤波器的频率响应，等价于逐个采样滤波（后面补一秒零，尾巴不会卷回开头）。"""
    n = 1 << (len(x) + sample_rate - 1).bit_length()
    zi = np.exp(-2j * np.pi * np.fft.rfftfreq(n))          # z⁻¹
    h = np.ones_like(zi)
    for b, a in _k_weighting(sample_rate):
        h *= (b[0] + b[1] * zi + b[2] * zi * zi) / (a[0] + a[1] * zi + a[2] * zi * zi)
    return np.fft.irfft(np.fft.rfft(x, n) * h, n)[:len(x)]


def integrated_loudness(x: np.ndarray, sample_rate: int) -> float:
    """BS.1770-4 的整体响度（LUFS）：400 ms 块、75% 重叠，-70 LUFS 绝对门限和 -10 LU 相对门限。
    各声道权重都是 1（四声道、八声道布局不是标准的环绕声位置）。"""
    block, hop = round(0.4 * sample_rate), round(0.1 * sample_rate)
    if len(x) < block:
        return -math.inf
    starts = np.arange(0, len(x) - block + 1, hop)
    power = np.zeros(len(starts))
    for c in range(x.shape[1]):
        energy = np.concatenate(([0.0], np.cumsum(_filtered(x[:, c], sample_rate) ** 2)))
        power += (energy[starts + block] - energy[starts]) / block

    def lufs(p):
        return -0.691 + 10 * np.log10(np.maximum(p, 1e-20))

    gated = power[lufs(power) > -70]
    if len(gated) == 0:
        return -math.inf
    gated = gated[lufs(gated) > lufs(gated.mean()) - 10]
    return float(lufs(gated.mean()))


@dataclass
class Stats:
    lufs: float
    peak: float                 # 采样峰值（dBFS）
    windows: list[float]        # 每 10 秒的平均电平（RMS，dBFS，所有声道）；最后不足 1 秒的零头不算


def audio_stats(path: Path, window: float = 10.0) -> Stats:
    x, sr = soundfile.read(str(path), dtype="float64", always_2d=True)

    def dbfs(v: float) -> float:
        return 20 * math.log10(v) if v > 1e-10 else -200.0

    n = round(window * sr)
    windows = [dbfs(math.sqrt(float(np.mean(x[i:i + n] ** 2)))) for i in range(0, len(x), n) if len(x) - i >= sr]
    return Stats(integrated_loudness(x, sr), dbfs(float(np.abs(x).max(initial=0.0))), windows)


# ── 命令行 ──────────────────────────────────────────────────────────────────


def find_arrangement(name: str) -> Arrangement:
    """编排标识（arrangements/ 下的文件夹名），或一个编排文件夹的路径。"""
    folder = Path(name)
    return load_arrangement(folder if (folder / "arrangement.toml").exists() else ARRANGEMENTS_DIR / name)


def _join(items, empty: str = "无") -> str:
    items = list(items)
    return "、".join(items) if items else empty


def report(sim: Simulation, scenario_name: str, channels: int, count: int, result: Render, out: Path) -> None:
    a = sim.arrangement
    layout = {2: "立体声", 4: "四声道", 8: "八声道"}[channels]
    starts = sum(1 for t, m in sim.score if m.address == "/s_new" and t < sim.duration)
    print(f"{a.title}（{a.id}，{a.mode}）· {scenario_name} · {sim.duration:g} 秒 · {layout}")
    print(f"乐谱 {count} 条指令（新建节点 {starts} 次）；渲染用时 {result.seconds:.1f} 秒，"
          f"扣掉启动和加载的 {result.load_seconds:.1f} 秒后是音频时长的 {100 * result.cpu(sim.duration):.2f}%"
          f"（CPU 的参考）")
    if result.ok:
        print(f"输出：{out}")
    else:
        print(f"渲染失败（scsynth 返回 {result.returncode}），没有写出文件")
    print(f"scsynth 报错：{len(result.errors) or '无'}")
    for line in result.errors[:20]:
        print(f"    {line}")
    if len(result.errors) > 20:
        print(f"    ……另有 {len(result.errors) - 20} 条")
    if result.ended_nodes:
        print(f"发给已经结束的节点的指令：{result.ended_nodes} 条（让位时声部恰好自然结束，装置上一样，无害）")

    total, cats = sim.budget
    parts = [f"{c} 最多 {n} 个" + (f"（预算 {cats[c]}）" if c in cats else "")
             for c, n in sorted(sim.peak_categories.items())]
    over = sim.peak_voices > total or any(n > cats.get(c, NO_BUDGET) for c, n in sim.peak_categories.items())
    note = ""
    if over and not sim.real_budget:
        note = "；超过了预算，装置上会让位或放弃，声音和负载以加 --real-budget 的结果为准"
    print(f"同时存在的声部最多 {sim.peak_voices} 个（配置预算 {total}）"
          + (f"，其中 {'，'.join(parts)}" if parts else "") + note)
    c = sim.counters
    print(f"引擎计数：让位 {c['yields']}，因预算放弃 {c['rejected']}，迟到丢弃 {c['late']}，"
          f"重复丢弃 {c['duplicates']}，重启 {c['restarts']}")
    print(f"缺少的素材：{_join(sim.missing)}")
    if sim.guessed:
        print(f"算不出长度、按 {DEFAULT_ONESHOT:g} 秒估算的单次声音：{_join(sorted(sim.guessed))}")
    if sim.endless:
        print(f"不会自己结束的单次声音（装置上会一直占着声部）：{_join(sorted(sim.endless))}")
    for item in sim.log:
        print(f"{'警告' if item['level'] == 'warning' else '错误'}：{item['text']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="离线渲染一份编排：真实的模式、声音引擎和音色，scsynth 非实时渲染成 WAV。")
    ap.add_argument("arrangement", help="编排标识（arrangements/ 下的文件夹名）或编排文件夹")
    ap.add_argument("scenario", type=Path, help="石头时间表（JSON，格式见脚本开头的说明）")
    ap.add_argument("out", type=Path, help="输出的 WAV 文件（32 位浮点）")
    ap.add_argument("--channels", type=int, choices=sorted(LAYOUTS), default=2,
                    help="声道数：2 立体声（默认）、4 四声道、8 八声道，音箱按预设布局")
    ap.add_argument("--level", type=float, help="用这个整体电平（dB）代替编排里的 level，调编排电平时用")
    ap.add_argument("--volume", type=float, help="总音量 0–1，默认与设置的默认值相同")
    ap.add_argument("--seed", type=int, default=1, help="模式的随机数种子（默认 1，同一种子的乐谱每次相同）")
    ap.add_argument("--real-budget", action="store_true", help="按配置里的声部预算让位和放弃，和装置一样（默认不限）；估算负载时要加")
    ap.add_argument("--sound", type=Path, help="声音素材库（包含 samples/ 的文件夹），默认与主机程序相同")
    ap.add_argument("--score", type=Path, help="把非实时乐谱另存到这个文件")
    ap.add_argument("--stats", action="store_true", help="另外打印响度（BS.1770 LUFS）、峰值和每 10 秒的平均电平")
    args = ap.parse_args(argv)

    cfg = load_config()
    scsynth = find_scsynth()
    quiet = logging.getLogger("soundmat")
    level = quiet.level
    try:
        if scsynth is None:
            raise FileNotFoundError("找不到 scsynth（安装 SuperCollider，或用环境变量 SOUNDMAT_SCSYNTH 指定）")
        if not any(cfg.synth.synthdefs_path.glob("*.scsyndef")):
            raise FileNotFoundError("音色还没有编译（先运行 scripts/compile_instruments.py）")
        arrangement = find_arrangement(args.arrangement)
        if args.level is not None:
            arrangement = dataclasses.replace(arrangement, level=args.level)
        scenario = Scenario.load(args.scenario)
        quiet.setLevel(logging.CRITICAL)        # 运行中的警告和错误不逐拍打印，汇总在最后
        sim = simulate(arrangement, scenario, config=cfg, channels=args.channels, volume=args.volume,
                       seed=args.seed, real_budget=args.real_budget, sound_dir=args.sound)
    except (FileNotFoundError, ValueError, LoadError) as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    finally:
        quiet.setLevel(level)

    count, result = render_simulation(sim, args.out, args.channels, cfg.sound.expected_sample_rate,
                                      args.score, scsynth)
    report(sim, args.scenario.name, args.channels, count, result, args.out)
    if not result.ok:
        print(result.output[-3000:], file=sys.stderr)
        return 1
    if args.stats:
        st = audio_stats(args.out)
        print(f"响度 {st.lufs:.1f} LUFS，峰值 {st.peak:.1f} dBFS")
        print("每 10 秒平均电平（dBFS）：" + " ".join(f"{v:.0f}" for v in st.windows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
