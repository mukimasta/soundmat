"""声池模式：网页原型 Ambient（Sound Pool）的移植，编排「冥想」用它（SONIFICATION「声池模式的运行」）。

依据是网页原型 ``web/soundmat/src/soundmat/``：``SoundMat.jsx`` 的放石头与换调、``pentatonic.js`` 的音高、
``audio/*.js`` 的各层声音。数值都照抄网页；音色本身（振荡器、滤波、包络、混响）在 ``instruments/pool/``，
这里只决定什么时候、在哪里、用什么音高发声。

一直有一层底音；每环一层，由内到外默认是：低音、中音（每颗石头一个持续的低音）、和声（每颗石头
一个声部，每隔几秒起一个长音）、中音符、高音符、钟声（整环一个节奏，按石头数取音、定间隔）、
天气（风雨按石头数此消彼长，四颗以上有雷）、自然（鸟鸣和水滴）。五声音阶，每个调停留 5–8 分钟后
沿五度圈换到下一个调，低音与和声随之换音。

和网页的不同：

- 位置：石头的声音（低音、和声、音符、钟声）放在石头的方位；底音、天气、自然不定位。
  空间化按半径决定声音多集中（越靠圆心越均匀地分到所有音箱），冥想的层大多在内环，照原样几乎都在
  正中；所以石头的半径先映射到 ``space.spread`` 的范围（默认 [0.85, 1]），内环也能用满左右。
- 网页上任何一颗石头的变化都会重建天气、自然和三个音符层（React 的写法所致），所以放一颗石头会让
  所有层很快各响一声、风声重新淡入。装置上每层只对自己那一环的变化反应，感知短暂抖动也不会牵动别的层。
- 同一个调里，同一个位置的低音音高不变（网页每次放下随机取音）：拿起再放下、感知抖动都不会换音。
- 一颗石头可能压到相邻两个区域，几乎同时有两个放下事件；同一环 0.3 秒内只立即响一次。
- 底音 ±2 dB 的音量起伏（网页是音色里 0.015 Hz 的 LFO）改由这里的 ``Breath`` 给出（``[breath]``）。
- 灯光：网页是八种环色的标记，这里改成一种颜色的低亮度明暗（``[light]``），跟着底音实际的音量走。
  底音听得出来的涌起落下主要是三路微失谐正弦的拍频，相位只有合成器知道，所以不在这里推算：底音的
  音色测量自己的音量送回来（``ctx.report("bed")``），灯光按它画。还没有测量值时（刚启动、离线渲染、
  测试）亮度停在中间。
"""
from __future__ import annotations

import math
import random
import uuid
from dataclasses import dataclass, field

from ...clock import Beat
from ...intent import BeatOutput, Event, ModeStatus, Position, SoundIntent, Source, Voice
from ...perception.model import MatEvent, MatSnapshot
from ...perception.zones import ZONES
from ..lights import warm_breathing
from ..mode import LoadError, LoadPlan, Mode

# ── 音高（pentatonic.js）────────────────────────────────────────────────────

# C 大调五声，按八度
PENTATONIC_C = {
    2: (65.41, 73.42, 82.41, 98.0, 110.0),
    3: (130.81, 146.83, 164.81, 196.0, 220.0),
    4: (261.63, 293.66, 329.63, 392.0, 440.0),
    5: (523.25, 587.33, 659.25, 784.0, 880.0),
}
# 五度圈 12 个调，相对 C 的半音数
KEY_NAMES = ("C", "G", "D", "A", "E", "B", "F#", "Db", "Ab", "Eb", "Bb", "F")
KEY_SEMITONES = (0, 7, 2, 9, 4, 11, 6, 1, 8, 3, 10, 5)
KEY_DWELL = (300.0, 480.0)          # 每个调停留 5–8 分钟

# ── 各层（audio/*.js）──────────────────────────────────────────────────────

LAYERS = ("low_drone", "mid_drone", "pad", "mid_notes", "high_notes", "weather", "bells", "nature")
DEFAULT_RINGS = LAYERS              # 由内到外，与网页由内到外的顺序相同（网页的第 0 环在最外）

DISTANT_POOL = (196.0, 220.0, 246.94, 293.66, 329.63)   # 远处偶发的音（C 调）
DISTANT_INTERVAL = (15.0, 30.0)

# 呼吸：底音音量起伏和灯光明暗共用（[breath]、[light]）
BREATH_PERIOD = 1 / 0.015           # 秒，约 67 秒（网页底音音量起伏 0.015 Hz）
BREATH_DEPTH_DB = 2.0               # 底音音量起伏 ±2 dB
BREATH_UPDATE = 0.25                # 每隔多久把呼吸值交给底音，合成器在这段时间里线性滑过去
LIGHT = {"color": (255, 255, 255), "breath_min": 0.0, "breath_max": 0.10, "stone_alpha": 0.30, "stone_width": 1}

# 低音：八度、第二个振荡器、音量、低通的明暗范围（droneVoice.js）
DRONES = {
    "low_drone": dict(octave=2, instrument="pool_drone_tri", amp=0.1, lfoLo=120.0, lfoHi=300.0),
    "mid_drone": dict(octave=3, instrument="pool_drone_saw", amp=0.08, lfoLo=180.0, lfoHi=450.0),
}

# 三个音符层：音池（C 调；第二颗石头起加上第二组）、间隔、音色（eventsVoice.js、pentatonic.js）
NOTE_POOLS = {
    "bells": ((523.25, 659.25, 784.0), (587.33, 880.0, 1046.5, 1174.7)),
    "mid_notes": ((130.81, 164.81, 196.0), (146.83, 220.0, 261.63)),
    "high_notes": ((523.25, 659.25, 784.0), (587.33, 880.0, 1046.5)),
}
FIXED_INTERVAL = {"bells": 6.0, "high_notes": 8.0}          # 前后再随机 ±0.5 秒
MID_INTERVALS = ((6.0, 12.0), (3.0, 8.0), (2.0, 5.0))      # 中音符：一颗、两颗、三颗以上

SPREAD = (0.85, 1.0)                # 圆心、垫面外缘的石头分别当作多大的半径来定位（space.spread）

IMMEDIATE_GAP = 0.3                 # 同一环两次"放下就响"至少隔开这么久

# 每颗石头一个的低音与和声计入"旋律"类的声部上限（配置 sound.voice_budget_categories，12 个）：
# 内两环摆满时最多 32 个低音，在 Pi 3B 上一个约占 2% 的 CPU，不加限制会超载
VOICE_CATEGORY = "melodic"

# 声部超出预算时：底音最重要，其次是持续的声音，再次是放下石头的反应，最后是自己在走的点缀
PRIORITY = {"bed": 3, "sustained": 2, "placed": 1, "ambient": 0}


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _light_config(c: dict) -> dict:
    """编排的 [light]：没写的项用默认值；不合法时报 LoadError。"""
    unknown = set(c) - set(LIGHT)
    if unknown:
        raise LoadError(f"light 里有未知的项：{' '.join(sorted(unknown))}")
    out = {**LIGHT, **c}
    color = out["color"]
    if not (isinstance(color, (list, tuple)) and len(color) == 3
            and all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 255 for x in color)):
        raise LoadError("light.color 应为三个 0–255 的整数")
    for key in ("breath_min", "breath_max", "stone_alpha"):
        if not _number(out[key]) or not 0 <= out[key] <= 1:
            raise LoadError(f"light.{key} 应在 0–1 之间")
    if out["breath_min"] > out["breath_max"]:
        raise LoadError("light.breath_min 不能大于 breath_max")
    w = out["stone_width"]
    if not isinstance(w, int) or isinstance(w, bool) or not 0 <= w <= 10:
        raise LoadError("light.stone_width 应为 0–10 的整数")
    return {"color": tuple(color), "breath_min": float(out["breath_min"]), "breath_max": float(out["breath_max"]),
            "stone_alpha": float(out["stone_alpha"]), "stone_width": w}


def _fmt(sec: float) -> str:
    s = max(0, int(sec))
    return f"{s // 60}:{s % 60:02d}"


class Key:
    """当前的调：从 C 开始，每停留 5–8 分钟沿五度圈换到下一个。``generation`` 每换一次加一。"""

    def __init__(self, rng: random.Random, t: float, dwell: tuple[float, float]):
        self.rng = rng
        self.dwell = dwell
        self.index = 0
        self.generation = 0
        self.next_change = t + rng.uniform(*dwell)

    def update(self, t: float) -> bool:
        if t < self.next_change:
            return False
        self.index = (self.index + 1) % len(KEY_NAMES)
        self.generation += 1
        self.next_change = t + self.rng.uniform(*self.dwell)
        return True

    @property
    def factor(self) -> float:
        return 2 ** (KEY_SEMITONES[self.index] / 12)

    @property
    def name(self) -> str:
        return KEY_NAMES[self.index]

    def pentatonic(self, octave: int) -> list[float]:
        return [hz * self.factor for hz in PENTATONIC_C[octave]]


@dataclass
class Frame:
    """一拍里各层共用的东西：时间、调、随机数，以及收集声部和事件。"""
    t: float
    key: Key
    rng: random.Random
    prefix: str
    counter: list[int]
    spread: tuple[float, float]
    voices: list[Voice] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)

    def event(self, name: str, instrument: str, bus: str, params: dict, *, after: float | None = 0.0,
              position: Position | None = None, priority: int = PRIORITY["ambient"]) -> None:
        """``after`` 是相对这一拍的秒数，给出时按时刻准时发声；None 表示立即（对放下石头的反应）。"""
        self.counter[0] += 1
        self.events.append(Event(
            id=f"{self.prefix}:{name}#{self.counter[0]}", time=None if after is None else self.t + after,
            source=Source("instrument", instrument), bus=bus, params=params,
            position=position, priority=priority,
        ))

    def position(self, zone: int) -> Position:
        """石头的声音的位置：区域的方位，半径映射到 ``spread`` 的范围。"""
        z = ZONES[zone]
        lo, hi = self.spread
        return Position(z.center_deg, lo + (hi - lo) * z.radius)


# ── 各层 ────────────────────────────────────────────────────────────────────


class Layer:
    """一环上的一层。``tick`` 拿到这一环此刻的石头（区域号，升序）和这一拍放下的石头。"""

    def __init__(self, name: str, ring: int):
        self.name = name
        self.ring = ring
        self.bus = f"ring{ring}"

    def tick(self, f: Frame, zones: list[int], placed: list[int]) -> None:
        raise NotImplementedError


class Breath:
    """底音音量和灯光共用的呼吸。``value`` 在 0–1 之间：从起点的 0.5 开始先升，
    ``0.5 + 0.5·sin(2π(t − 起点)/周期)``，和网页底音音量 LFO 的波形与起始相位相同。"""

    def __init__(self, started: float, period: float, depth_db: float):
        self.started = started
        self.period = period
        self.depth_db = depth_db

    def phase(self, t: float) -> float:
        return (2 * math.pi * (t - self.started) / self.period) % (2 * math.pi)

    def value(self, t: float) -> float:
        return 0.5 + 0.5 * math.sin(self.phase(t))


class Bed:
    """底音（一直在响）和远处偶尔的一声（baseLayer.js）。两者的音量都跟着呼吸起伏。"""

    def __init__(self, rng: random.Random, t: float, breath: Breath):
        self.breath = breath
        self.next_distant = t + rng.uniform(*DISTANT_INTERVAL)

    def tick(self, f: Frame) -> None:
        # 呼吸值每 BREATH_UPDATE 秒交一次，给的是这一段结束时的值，合成器在这段时间里线性滑过去，
        # 所以听到的音量与灯光同一时刻取的值一致（只差折线和正弦的一点点）
        b = self.breath
        k = math.floor((f.t - b.started) / BREATH_UPDATE) + 1
        f.voices.append(Voice(
            id="bed", source=Source("instrument", "pool_bed"), bus="bed",
            params={"t": f.key.factor, "breath": b.value(b.started + k * BREATH_UPDATE), "depth": b.depth_db},
            fade_in=0.05, fade_out=2.0, priority=PRIORITY["bed"],
        ))
        if f.t >= self.next_distant:
            self.next_distant = f.t + f.rng.uniform(*DISTANT_INTERVAL)
            f.event("distant", "pool_distant", "bed", {
                "freq": f.rng.choice(DISTANT_POOL) * f.key.factor,
                "decay": f.rng.uniform(6, 10),
                "amp": 10 ** (f.rng.uniform(-40, -34) / 20),
                "volPhase": b.phase(f.t), "volHz": 1 / b.period, "depth": b.depth_db,
            })


class Drones(Layer):
    """每颗石头一个持续的低音（droneVoice.js）。音高在五声音阶里随机取，同一个调里同一个位置不变；
    换调时所有低音换成新的音（旧的 1.5 秒淡出、新的 3 秒淡入）。"""

    def __init__(self, name: str, ring: int):
        super().__init__(name, ring)
        self.spec = DRONES[name]
        self.chosen: dict[int, dict] = {}       # 区域 → 这个调里选定的音高和慢速变化的周期
        self.generation = -1

    def tick(self, f: Frame, zones: list[int], placed: list[int]) -> None:
        if f.key.generation != self.generation:
            self.generation = f.key.generation
            self.chosen.clear()
        for z in zones:
            p = self.chosen.get(z)
            if p is None:
                p = self.chosen[z] = {
                    "freq": f.rng.choice(f.key.pentatonic(self.spec["octave"])),
                    "lfoPeriod": f.rng.uniform(120, 200),
                    "driftPeriod": f.rng.uniform(180, 300),
                }
            f.voices.append(Voice(
                id=f"{self.name}.{z}.k{self.generation}", source=Source("instrument", self.spec["instrument"]),
                bus=self.bus, params={**p, "amp": self.spec["amp"],
                                      "lfoLo": self.spec["lfoLo"], "lfoHi": self.spec["lfoHi"]},
                fade_in=3.0, fade_out=1.5, position=f.position(z), priority=PRIORITY["sustained"],
                category=VOICE_CATEGORY,
            ))


class Pads(Layer):
    """每颗石头一个和声声部，放下时起第一个音，之后每隔固定的 4–8 秒再起一个（padVoice.js）。
    每个音的音高、起音、长度、淡出都随机。换调时整个声部换新的。"""

    def __init__(self, name: str, ring: int):
        super().__init__(name, ring)
        self.pads: dict[int, dict] = {}         # 区域 → 声部状态

    def tick(self, f: Frame, zones: list[int], placed: list[int]) -> None:
        for z in [z for z in self.pads if z not in zones]:
            del self.pads[z]
        for z in zones:
            pad = self.pads.get(z)
            if pad is None or pad["generation"] != f.key.generation:
                interval = f.rng.uniform(4, 8)
                pad = self.pads[z] = {"generation": f.key.generation, "interval": interval,
                                      "next": f.t + interval, "params": {"n": 1.0, **self._note(f)},
                                      "lfoPeriod": f.rng.uniform(90, 150)}
            elif f.t >= pad["next"]:
                pad["next"] = max(pad["next"] + pad["interval"], f.t)
                pad["params"] = {"n": pad["params"]["n"] + 1, **self._note(f)}
            f.voices.append(Voice(
                id=f"{self.name}.{z}.k{pad['generation']}", source=Source("instrument", "pool_pad"),
                bus=self.bus, params={**pad["params"], "lfoPeriod": pad["lfoPeriod"], "lfoLo": 800.0,
                                      "lfoHi": 1200.0, "noteAmp": 0.03, "amp": 0.6},
                fade_in=2.0, fade_out=1.5, position=f.position(z), priority=PRIORITY["sustained"],
                category=VOICE_CATEGORY,
            ))

    @staticmethod
    def _note(f: Frame) -> dict:
        return {"freq": f.rng.choice(f.key.pentatonic(4)), "noteAtk": f.rng.uniform(2, 4),
                "hold": f.rng.uniform(6, 12), "fall": f.rng.uniform(3, 6)}


class Notes(Layer):
    """整环一个节奏的音符：钟声、中音符、高音符（eventsVoice.js）。放下石头立即响一声，之后钟声每
    6 秒、高音符每 8 秒（各 ±0.5 秒），中音符按石头数随机间隔；音从这一环的某颗石头的方位发出。"""

    def __init__(self, name: str, ring: int):
        super().__init__(name, ring)
        self.count = 0
        self.next: float | None = None
        self.last_immediate = -1e9

    def tick(self, f: Frame, zones: list[int], placed: list[int]) -> None:
        n = len(zones)
        if n == 0:
            self.count, self.next = 0, None
            return
        if n != self.count:
            # 这一环的石头变了，网页会重建这一层：放下时立即响，拿起时 0.3–1.5 秒后再响。
            # 刚刚立即响过（一颗石头压到相邻两个区域）就不再响，节奏也不变
            self.count = n
            if not placed:
                self.next = f.t + f.rng.uniform(0.3, 1.5)
            elif f.t - self.last_immediate >= IMMEDIATE_GAP:
                self.last_immediate = f.t
                self._strike(f, placed[-1], immediate=True)
                self.next = f.t + self._interval(f)
        if self.next is not None and f.t >= self.next:
            self._strike(f, f.rng.choice(zones), immediate=False)
            self.next = f.t + self._interval(f)

    def _interval(self, f: Frame) -> float:
        if self.name in FIXED_INTERVAL:
            return FIXED_INTERVAL[self.name] + f.rng.uniform(-0.5, 0.5)
        return f.rng.uniform(*MID_INTERVALS[min(self.count - 1, 2)])

    def _strike(self, f: Frame, zone: int, immediate: bool) -> None:
        first, more = NOTE_POOLS[self.name]
        pool = first + (more if self.count >= 2 else ())
        freq = f.rng.choice(pool) * f.key.factor
        if self.name == "bells":
            instrument = "pool_bell"
            params = {"freq": freq, "amp": f.rng.uniform(0.02, 0.06), "decay": f.rng.uniform(10, 18)}
        elif self.name == "mid_notes":
            instrument = "pool_note"
            params = {"freq": freq, "tri": 1.0, "noteAtk": 0.08, "decay": f.rng.uniform(4, 7),
                      "amp": f.rng.uniform(0.02, 0.05)}
        else:
            instrument = "pool_note_echo"
            params = {"freq": freq, "tri": 0.0, "noteAtk": 0.005, "decay": f.rng.uniform(2, 5),
                      "amp": f.rng.uniform(0.015, 0.04)}
        f.event(self.name, instrument, self.bus, params, after=None if immediate else 0.0,
                position=f.position(zone), priority=PRIORITY["placed" if immediate else "ambient"])


class Weather(Layer):
    """风和雨（weatherVoice.js）。一颗石头只有风，之后每多一颗风减一分、雨加一分，四颗时只剩雨，
    五颗以上雨更大；四颗起有雷，石头越多越频繁，三颗变四颗时立即打一次雷。风每 8 秒有四成机会起一阵。"""

    def __init__(self, name: str, ring: int):
        super().__init__(name, ring)
        self.count = 0
        self.voice: dict | None = None          # 声部存在时的参数
        self.next_gust = 0.0
        self.settle: tuple[float, float, float] | None = None   # 阵风回落：(时刻, 目标, 用时)
        self.next_thunder: float | None = None
        self.unboost: tuple[float, float] | None = None         # 雷声过后雨声回落：(时刻, 用时)

    def tick(self, f: Frame, zones: list[int], placed: list[int]) -> None:
        n = len(zones)
        if n == 0:
            self.count, self.voice, self.next_thunder, self.settle, self.unboost = 0, None, None, None, None
            return
        if self.voice is None:
            self.voice = {"wind": 0.03, "windTime": 4.0, "boost": 1.0, "boostTime": 0.5,
                          "driftPeriod": f.rng.uniform(48, 78), "rainPeriod": f.rng.uniform(60, 90)}
            self.next_gust = f.t + 8.0
        if n != self.count:
            if n == 4 and self.count == 3:
                self._thunder(f)
            self.count = n
            self.next_thunder = f.t + self._thunder_wait(f) if n >= 4 else None
        v = self.voice
        v["windMix"] = 0.0 if n >= 5 else (4 - min(n, 4)) / 3
        v["rain"] = (0.0 if n <= 1 else 1.0 if n >= 5 else (n - 1) / 3) * (1 + (n - 5) * 0.11 if n >= 5 else 1.0)

        if f.t >= self.next_gust:
            self.next_gust += 8.0
            if f.rng.random() <= 0.4:
                v["wind"], v["windTime"] = f.rng.uniform(0.06, 0.1), f.rng.uniform(1, 3)
                self.settle = (f.t + f.rng.uniform(2, 4), f.rng.uniform(0.02, 0.04), f.rng.uniform(2, 5))
        if self.settle and f.t >= self.settle[0]:
            _, v["wind"], v["windTime"] = self.settle
            self.settle = None
        if self.next_thunder is not None and f.t >= self.next_thunder:
            if f.rng.random() < self._thunder_chance():
                self._thunder(f)
            self.next_thunder = f.t + self._thunder_wait(f)
        if self.unboost and f.t >= self.unboost[0]:
            v["boost"], v["boostTime"] = 1.0, self.unboost[1]
            self.unboost = None

        f.voices.append(Voice(
            id=self.name, source=Source("instrument", "pool_weather"), bus=self.bus, params=dict(v),
            fade_in=0.05, fade_out=1.5, priority=PRIORITY["sustained"],
        ))

    def _thunder_chance(self) -> float:
        n = self.count
        return 0.0 if n < 4 else 0.14 if n == 4 else min(0.72, 0.2 + (n - 5) * 0.1)

    def _thunder_wait(self, f: Frame) -> float:
        k = max(0, self.count - 4)
        return f.rng.uniform(max(7.0, 20.0 - k * 2.4), max(12.0, 38.0 - k * 4.8))

    def _thunder(self, f: Frame) -> None:
        atk, sus, rel = f.rng.uniform(0.38, 0.72), f.rng.uniform(1.5, 2.6), f.rng.uniform(6, 10)
        f.event("thunder", "pool_thunder", self.bus, {
            "tAtk": atk, "sus": sus, "tRel": rel, "amp": f.rng.uniform(0.44, 0.62),
            "fStart": f.rng.uniform(70, 115), "fEnd": f.rng.uniform(380, 560),
            "airFreq": f.rng.uniform(800, 1250), "airGain": f.rng.uniform(0.24, 0.42),
        })
        if self.count >= 2 and self.voice is not None:      # 有雨时，雷声让雨声加强，雷声淡出时回落
            self.voice["boost"], self.voice["boostTime"] = f.rng.uniform(1.5, 2.25), f.rng.uniform(0.35, 0.65)
            self.unboost = (f.t + atk + sus, rel + 0.6)


class Nature(Layer):
    """鸟鸣和水滴（natureVoice.js）。放下石头时立即一滴水；之后按石头数随机间隔，可能安静、
    一滴水或者鸟鸣，石头越多越密、鸟越多（一问一答、两只、一串）。"""

    def __init__(self, name: str, ring: int):
        super().__init__(name, ring)
        self.count = 0
        self.next: float | None = None
        self.last_immediate = -1e9

    def tick(self, f: Frame, zones: list[int], placed: list[int]) -> None:
        if placed and f.t - self.last_immediate >= IMMEDIATE_GAP:
            self.last_immediate = f.t
            self._drop(f, after=None, priority=PRIORITY["placed"])
        n = len(zones)
        if n == 0:
            self.count, self.next = 0, None
            return
        if n != self.count:
            self.count = n
            self.next = f.t + f.rng.uniform(*self._timing()[:2])
        if self.next is not None and f.t >= self.next:
            lo, hi, p_bird, p_drop = self._timing()
            silence = max(0.04, 1 - p_bird - p_drop)
            r = f.rng.random()
            if r < silence:
                pass
            elif r < silence + p_drop:
                self._drop(f)
            else:
                self._birds(f)
            self.next = f.t + f.rng.uniform(lo, hi)

    def _timing(self) -> tuple[float, float, float, float]:
        """(最短间隔, 最长间隔, 鸟的概率, 水滴的概率)"""
        n = self.count
        table = {1: (4.0, 10.0, 0.06, 0.28), 2: (3.0, 7.0, 0.09, 0.36), 3: (2.0, 4.6, 0.1, 0.42),
                 4: (1.3, 3.2, 0.11, 0.48)}
        if n in table:
            return table[n]
        ex = n - 5
        return (max(0.7, 1.1 - ex * 0.13), max(1.4, 2.3 - ex * 0.22),
                min(0.2, 0.12 + ex * 0.018), min(0.52, 0.44 + ex * 0.032))

    def _drop(self, f: Frame, after: float | None = 0.0, priority: int = PRIORITY["ambient"]) -> None:
        f.event("drop", "pool_drop", self.bus, {
            "freq": f.rng.uniform(800, 1200), "decay": f.rng.uniform(1, 2), "amp": f.rng.uniform(0.055, 0.095),
        }, after=after, priority=priority)

    def _birds(self, f: Frame) -> None:
        n, br = self.count, f.rng.random()
        if n >= 5:
            kind = "chorus" if br < 0.34 else "conversation" if br < 0.82 else "chirp"
        elif n == 4:
            kind = "chorus" if br < 0.32 else "conversation"
        elif n == 3:
            kind = "conversation"
        else:
            kind = "chirp"
        if kind == "chirp":
            self._chirp(f, 0.0, trill=True)
        elif kind == "chorus":                  # 极短间隔两声：近处两只鸟或同一只连叫
            self._chirp(f, 0.0)
            self._chirp(f, f.rng.uniform(0.07, 0.17))
        else:                                   # 一问一答，有时再接一声
            self._chirp(f, 0.0)
            d1 = f.rng.uniform(0.5, 1.5)
            self._chirp(f, d1)
            if f.rng.random() < 0.5:
                self._chirp(f, d1 + f.rng.uniform(0.5, 1.4))

    def _chirp(self, f: Frame, after: float, trill: bool = False) -> None:
        if trill and f.rng.random() < 0.38:
            # 一串：网页写的间隔单位是毫秒而数值是零点几，所以三四声实际上同时发出，听起来是一声更亮的啾
            for _ in range(3 + f.rng.randrange(2)):
                self._sweep(f, after, f.rng.uniform(0.045, 0.1), (2100, 2800), (3000, 3500), (2000, 2700))
            return
        self._sweep(f, after, f.rng.uniform(0.15, 0.3), (1850, 2150), (3200, 3600), (1900, 2400))

    def _sweep(self, f: Frame, after: float, dur: float, start, peak, end) -> None:
        f.event("chirp", "pool_chirp", self.bus, {
            "dur": dur, "up": dur * f.rng.uniform(0.42, 0.54), "decay": max(0.06, dur * 0.88),
            "f0": f.rng.uniform(*start), "f1": f.rng.uniform(*peak), "f2": f.rng.uniform(*end),
            "amp": f.rng.uniform(0.14, 0.28),
        }, after=after)


LAYER_CLASSES: dict[str, type[Layer]] = {
    "low_drone": Drones, "mid_drone": Drones, "pad": Pads, "mid_notes": Notes, "high_notes": Notes,
    "weather": Weather, "bells": Notes, "nature": Nature,
}
INSTRUMENTS = frozenset({
    "pool_bed", "pool_distant", "pool_drone_tri", "pool_drone_saw", "pool_pad", "pool_bell", "pool_note", "pool_note_echo",
    "pool_weather", "pool_thunder", "pool_drop", "pool_chirp",
})


class PoolMode(Mode):
    name = "pool"

    def load(self) -> LoadPlan:
        c = self.arrangement.content
        rings = list(c.get("rings", DEFAULT_RINGS))
        if len(rings) != 8:
            raise LoadError("rings 应有 8 项：由内到外每环放哪一层")
        for layer in rings:
            if layer not in LAYERS:
                raise LoadError(f"未知的层 {layer}，可选：{' '.join(LAYERS)}")
        if len(set(rings)) != len(rings):
            raise LoadError("rings 里同一层出现了两次")
        dwell = c.get("music", {}).get("key_dwell", KEY_DWELL)
        if len(dwell) != 2 or not 0 < dwell[0] <= dwell[1]:
            raise LoadError("music.key_dwell 应为 [最短, 最长]（秒）")
        spread = c.get("space", {}).get("spread", SPREAD)
        if len(spread) != 2 or not 0 <= spread[0] <= spread[1] <= 1:
            raise LoadError("space.spread 应为 [圆心, 外缘]，0–1 之间")
        breath = c.get("breath", {})
        period, depth = breath.get("period", BREATH_PERIOD), breath.get("sound_depth_db", BREATH_DEPTH_DB)
        if not _number(period) or period < 1:
            raise LoadError("breath.period 应为不小于 1 的秒数")
        if not _number(depth) or not 0 <= depth <= 12:
            raise LoadError("breath.sound_depth_db 应在 0–12 dB 之间")
        self.rings = rings
        self.dwell = (float(dwell[0]), float(dwell[1]))
        self.spread = (float(spread[0]), float(spread[1]))
        self.breath_period, self.breath_depth = float(period), float(depth)
        self.light = _light_config(c.get("light", {}))
        return LoadPlan(instruments=INSTRUMENTS, buses=("bed",) + tuple(f"ring{r}" for r in range(8)),
                        fx="sm_fx_pool")

    def start(self, t: float) -> None:
        self.rng = random.Random(self.ctx.seed)
        # 事件标识的前缀：同一份编排切换到自己时，两个实例的事件标识也不会相同
        self.prefix = f"{self.arrangement.id}.{uuid.uuid4().hex[:6]}"
        self.counter = [0]
        self.key = Key(self.rng, t, self.dwell)
        self.breath = Breath(t, self.breath_period, self.breath_depth)
        self.bed_level: float | None = None
        self.bed = Bed(self.rng, t, self.breath)
        self.layers = [LAYER_CLASSES[name](name, ring) for ring, name in enumerate(self.rings)]

    def _bed_level(self) -> float:
        """底音此刻测得的音量（0–1）。偶尔收不到时沿用上一个值；从没收到过时停在中间。"""
        got = self.ctx.report("bed")
        if got:
            self.bed_level = min(1.0, max(0.0, got[0]))
        return 0.5 if self.bed_level is None else self.bed_level

    def tick(self, beat: Beat, snapshot: MatSnapshot, events: list[MatEvent]) -> BeatOutput:
        t = beat.t
        self.key.update(t)
        by_ring: dict[int, list[int]] = {r: [] for r in range(8)}
        for z in sorted(snapshot.state.occupied):
            by_ring[ZONES[z].ring].append(z)
        placed: dict[int, list[int]] = {r: [] for r in range(8)}
        for e in events:
            if e.kind == "place":
                placed[ZONES[e.zone].ring].append(e.zone)

        f = Frame(t, self.key, self.rng, self.prefix, self.counter, self.spread)
        self.bed.tick(f)
        for layer in self.layers:
            layer.tick(f, by_ring[layer.ring], placed[layer.ring])
        remaining = self.key.next_change - t
        return BeatOutput(
            sound=SoundIntent(tuple(f.voices), tuple(f.events)),
            light=warm_breathing(self._bed_level(), snapshot.state.occupied, self.ctx.led_count, **self.light),
            status=ModeStatus(text=f"五声 {self.key.name} 调 · {_fmt(remaining)} 后换调"),
        )
