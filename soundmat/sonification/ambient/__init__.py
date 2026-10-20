"""Ambient 模式：按环编排的环境声（SONIFICATION「Ambient 模式的运行」）。

每环若干角色，每个角色有一种行为：
- 持续（sustained）：所在环有石头就响；按石头数分档，档位改变时标识随之改变，旧档淡出、新档淡入。
- 间歇（intermittent）：所在环有石头时激活，以编排给出范围内的随机间隔触发。
- 触发（trigger）：这一拍积累的放下事件，在对应环上各触发一次。
角色可以带条件：``when_rings`` 里的环都有石头、``unless_rings`` 里的环都没有石头时才生效。

位置策略（``position``）：``zone`` 放下石头的区域中心（触发的默认）、``centroid`` 这一环所有石头的
方位重心、``random`` 随机方位（间歇的默认）、``none`` 不定位（持续的默认）。

内容格式见 docs/implementation/ARRANGEMENTS.md。
"""
from __future__ import annotations

import math
import random
import uuid
from dataclasses import dataclass, field
from typing import Any

from ...clock import Beat
from ...perception.model import MatEvent, MatSnapshot
from ...perception.zones import RING_CENTERS, MAT_RADIUS, ZONES, zones_in_ring
from ...intent import BeatOutput, Event, LightIntent, ModeStatus, Position, SoundIntent, Source, Voice
from ..lights import breathing_marks
from ..mode import LoadError, LoadPlan, Mode, arrivals

BEHAVIORS = ("sustained", "intermittent", "trigger")
RESERVED = {"behavior", "instrument", "samples", "tiers", "interval", "position",
            "when_rings", "unless_rings", "priority"}
DEFAULT_POSITION = {"sustained": "none", "intermittent": "random", "trigger": "zone"}
# 声部超出预算时：持续的底层高于触发，触发高于间歇的点缀
DEFAULT_PRIORITY = {"sustained": 2, "trigger": 1, "intermittent": 0}


@dataclass
class Role:
    ring: int
    name: str
    behavior: str
    instrument: str | None
    samples: list[str]
    tiers: list[tuple[int, str, dict]]
    interval: tuple[float, float] | None
    position: str
    when: tuple[int, ...]
    unless: tuple[int, ...]
    priority: int
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"r{self.ring}.{self.name}"


def _midi_freq(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


class AmbientMode(Mode):
    name = "ambient"

    # ── 加载 ────────────────────────────────────────────────────────────

    def load(self) -> LoadPlan:
        c = self.arrangement.content
        music = c.get("music", {})
        self.root = float(music.get("root", 60))
        self.scale = [float(x) for x in music.get("scale", [0, 2, 4, 7, 9])]
        if not self.scale:
            raise LoadError("music.scale 不能为空")
        self.defaults = dict(c.get("defaults", {}))
        self.samples: dict[str, tuple[str, dict]] = {}
        for sid, cfg in c.get("samples", {}).items():
            if "file" not in cfg:
                raise LoadError(f"素材 {sid} 缺少 file")
            self.samples[sid] = (cfg["file"], {k: v for k, v in cfg.items() if k != "file"})

        self.roles: list[Role] = []
        for ring_key, roles in c.get("rings", {}).items():
            ring = int(ring_key)
            if not 0 <= ring < 8:
                raise LoadError(f"环号超出范围：{ring}")
            for name, cfg in roles.items():
                self.roles.append(self._role(ring, name, cfg))
        if not self.roles:
            raise LoadError("编排里没有任何角色")
        _numeric(self.defaults)
        for _, sp in self.samples.values():
            _numeric(sp)
        for r in self.roles:
            _numeric(r.params)
            for t in r.tiers:
                _numeric(t[2])

        assets = set()
        instruments = set()
        for r in self.roles:
            if r.instrument:
                instruments.add(r.instrument)
            for sid in r.samples + [t[1] for t in r.tiers]:
                assets.add(self.samples[sid][0])
        return LoadPlan(assets=frozenset(assets), instruments=frozenset(instruments))

    def _role(self, ring: int, name: str, cfg: dict) -> Role:
        where = f"第 {ring} 环的 {name}"
        behavior = cfg.get("behavior")
        if behavior not in BEHAVIORS:
            raise LoadError(f"{where}：behavior 应为 {' / '.join(BEHAVIORS)}")
        instrument = cfg.get("instrument")
        samples = list(cfg.get("samples", []))
        tiers = []
        for t in cfg.get("tiers", []):
            tiers.append((int(t["count"]), t["sample"], {k: v for k, v in t.items() if k not in ("count", "sample")}))
        tiers.sort(key=lambda t: t[0])
        if not instrument and not samples and not tiers:
            raise LoadError(f"{where}：需要 instrument、samples 或 tiers")
        for sid in samples + [t[1] for t in tiers]:
            if sid not in self.samples:
                raise LoadError(f"{where}：引用了不存在的素材 {sid}")
        interval = None
        if behavior == "intermittent":
            iv = cfg.get("interval")
            if not iv or len(iv) != 2 or not 0 < iv[0] <= iv[1]:
                raise LoadError(f"{where}：间歇角色需要 interval = [最短, 最长]（秒）")
            interval = (float(iv[0]), float(iv[1]))
        position = cfg.get("position", DEFAULT_POSITION[behavior])
        if position not in ("zone", "centroid", "random", "none"):
            raise LoadError(f"{where}：未知的 position {position}")
        return Role(
            ring=ring, name=name, behavior=behavior, instrument=instrument, samples=samples,
            tiers=tiers, interval=interval, position=position,
            when=tuple(cfg.get("when_rings", ())), unless=tuple(cfg.get("unless_rings", ())),
            priority=int(cfg.get("priority", DEFAULT_PRIORITY[behavior])),
            params={k: v for k, v in cfg.items() if k not in RESERVED},
        )

    # ── 运行 ────────────────────────────────────────────────────────────

    def start(self, t: float) -> None:
        self.rng = random.Random(self.ctx.seed)
        # 事件标识的前缀：同一份编排切换到自己时，两个实例的事件标识也不会相同
        self.prefix = f"{self.arrangement.id}.{uuid.uuid4().hex[:6]}"
        self.next_fire: dict[str, float] = {}
        self.fired = 0

    def tick(self, beat: Beat, snapshot: MatSnapshot, events: list[MatEvent]) -> BeatOutput:
        t = beat.t
        counts = snapshot.state.ring_counts
        by_ring: dict[int, list[int]] = {}
        for z in snapshot.state.occupied:
            by_ring.setdefault(ZONES[z].ring, []).append(z)

        voices: list[Voice] = []
        out_events: list[Event] = []
        placed = arrivals(events)

        for role in self.roles:
            active = self._active(role, counts)
            if role.behavior == "sustained" and active:
                voices.append(self._sustained(role, counts[role.ring], by_ring.get(role.ring, [])))
            elif role.behavior == "intermittent":
                if not active:
                    self.next_fire.pop(role.key, None)
                    continue
                due = self.next_fire.get(role.key)
                if due is None:
                    self.next_fire[role.key] = t + self.rng.uniform(*role.interval)
                elif t >= due:
                    out_events.append(self._oneshot(role, None, by_ring.get(role.ring, [])))
                    self.next_fire[role.key] = t + self.rng.uniform(*role.interval)
            elif role.behavior == "trigger" and self._conditions(role, counts):
                for e in placed:
                    if ZONES[e.zone].ring == role.ring:
                        out_events.append(self._oneshot(role, e.zone, by_ring.get(role.ring, [])))

        return BeatOutput(
            sound=SoundIntent(tuple(voices), tuple(out_events)),
            light=self._light(t, snapshot),
            status=ModeStatus(text=f"每环一层 · {self._speakers_text()}"),
        )

    def _conditions(self, role: Role, counts) -> bool:
        return all(counts[w] > 0 for w in role.when) and not any(counts[u] > 0 for u in role.unless)

    def _active(self, role: Role, counts) -> bool:
        return counts[role.ring] > 0 and self._conditions(role, counts)

    def _sample_params(self, sid: str, *layers: dict) -> tuple[str, dict]:
        file, sp = self.samples[sid]
        params: dict = {}
        for layer in (self.defaults, sp, *layers):
            params.update(layer)
        return file, params

    def _sustained(self, role: Role, count: int, zones: list[int]) -> Voice:
        key = role.key
        if role.instrument:
            source = Source("instrument", role.instrument)
            params = dict(role.params)
        else:
            if role.tiers:
                eligible = [t for t in role.tiers if t[0] <= count] or role.tiers[:1]
                _, sid, tier_params = eligible[-1]
                key = f"{key}.{sid}"
            else:
                sid, tier_params = role.samples[0], {}
            file, params = self._sample_params(sid, role.params, tier_params)
            source = Source("sample", file)
        fade_in = float(params.pop("atk", 0.05))
        fade_out = float(params.pop("rel", 0.5))
        return Voice(
            id=key, source=source, bus=f"ring{role.ring}", params=_numeric(params),
            fade_in=fade_in, fade_out=fade_out,
            position=self._position(role, None, zones), priority=role.priority,
        )

    def _oneshot(self, role: Role, zone: int | None, zones: list[int]) -> Event:
        self.fired += 1
        if role.instrument:
            source = Source("instrument", role.instrument)
            params = dict(role.params)
            if "freq" not in params:
                params["freq"] = self._slot_freq(zone) if zone is not None else self._random_freq()
        else:
            sid = self.rng.choice(role.samples) if role.samples else role.tiers[0][1]
            file, params = self._sample_params(sid, role.params)
            source = Source("sample", file)
        return Event(
            id=f"{self.prefix}:{role.key}#{self.fired}", time=None, source=source,   # 对动作的反应：立即
            bus=f"ring{role.ring}", params=_numeric(params),
            position=self._position(role, zone, zones), priority=role.priority,
        )

    def _position(self, role: Role, zone: int | None, zones: list[int]) -> Position | None:
        ring_radius = RING_CENTERS[role.ring] / MAT_RADIUS
        kind = role.position
        if kind == "zone" and zone is not None:
            z = ZONES[zone]
            return Position(z.center_deg, z.radius)
        if kind == "centroid" or (kind == "zone" and zone is None):
            if not zones:
                return None
            x = sum(math.sin(math.radians(ZONES[i].center_deg)) for i in zones)
            y = sum(math.cos(math.radians(ZONES[i].center_deg)) for i in zones)
            if abs(x) < 1e-9 and abs(y) < 1e-9:
                return None  # 石头均匀分布在一圈上，没有方向
            return Position(math.degrees(math.atan2(x, y)) % 360, ring_radius)
        if kind == "random":
            return Position(self.rng.uniform(0, 360), ring_radius)
        return None

    def _slot_freq(self, zone: int) -> float:
        """扇区 → 音高：两半对称映射到同一音阶（与第一版一致）。"""
        z = ZONES[zone]
        n = zones_in_ring(z.ring)
        mirrored = min(z.slot, n - z.slot)
        deg = self.scale[mirrored % len(self.scale)]
        octave = mirrored // len(self.scale)
        return _midi_freq(self.root + 12 * octave + deg)

    def _random_freq(self) -> float:
        octave = self.rng.randrange(2)
        return _midi_freq(self.root + 12 * octave + self.rng.choice(self.scale))

    def _speakers_text(self) -> str:
        layout = self.ctx.setting("sound.layout", None) or {}
        n = len(layout.get("azimuths", [])) or 2
        return "左右两只音箱" if n == 2 else f"{n} 只音箱"

    def _light(self, t: float, snapshot: MatSnapshot) -> LightIntent:
        return breathing_marks(t, snapshot.state.occupied, self.ctx.led_count)


def _numeric(params: dict) -> dict[str, float]:
    """交给合成器服务的参数只能是数值；布尔值转成 0/1。"""
    out = {}
    for k, v in params.items():
        if isinstance(v, bool):
            out[k] = 1.0 if v else 0.0
        elif isinstance(v, (int, float)):
            out[k] = float(v)
        else:
            raise LoadError(f"参数 {k} 不是数值：{v!r}")
    return out
