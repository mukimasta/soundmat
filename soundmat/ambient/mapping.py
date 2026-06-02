"""Mapper + 数据类型。

VoiceSpec / TriggerSpec / GeneratorSpec / MapResult：mapper 的输出合约。
KyotoMapper：《京都岚山》完整映射，从 sonification/soundmat/mapping/kyoto.py 迁移。

三种 mode：
  sustained   → 有石头时持续响；VoicePool reconcile 管淡入/淡出
  generator   → 有石头时激活间歇随机触发源；VoicePool pump 按随机间隔发声
  trigger     → 石头放下那一帧触发一次
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Protocol

from .. import config
from .state import Events, State

VoiceKey = tuple

# manifest 中不当 SynthDef 参数的保留键
_RESERVED = {"mode", "samples", "sample", "file", "tiers", "count", "synthdef", "interval", "tune"}

# C 大调五声音阶级数（半音）：C D E G A
_PENTATONIC = [0, 2, 4, 7, 9]


def _params(*layers) -> dict:
    """合并多层配置，过滤保留键，后层覆盖前层。"""
    out: dict = {}
    for layer in layers:
        for k, v in (layer or {}).items():
            if k not in _RESERVED:
                out[k] = v
    return out


def _pan(slice_idx: int, n_slices: int) -> float:
    return math.sin(2 * math.pi * slice_idx / n_slices)


def _pick_tier(cfg: dict, count: int) -> tuple[str, dict]:
    """有 tiers 按石头数选档（取 count<=当前 的最大档），否则用 samples[0]。"""
    tiers = cfg.get("tiers")
    if tiers:
        chosen = max(
            (t for t in tiers if t["count"] <= count),
            key=lambda t: t["count"],
            default=tiers[0],
        )
        return chosen["sample"], chosen
    return cfg["samples"][0], {}


def _midi_to_freq(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _scale_freqs(root_midi: int = 60, octaves: int = 2, degrees=_PENTATONIC) -> list[float]:
    return [_midi_to_freq(root_midi + 12 * o + d) for o in range(octaves) for d in degrees]


def _slice_freq(slice_idx: int, n_slices: int, degrees=_PENTATONIC, root_midi: int = 60) -> float:
    """扇区 → 音高：两半对称映射到同一音阶。"""
    mirrored = min(slice_idx, n_slices - slice_idx)
    deg_idx = mirrored % len(degrees)
    octave = mirrored // len(degrees)
    return _midi_to_freq(root_midi + 12 * octave + degrees[deg_idx])


# ── 数据类型 ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class VoiceSpec:
    """持续 voice：sample（采样）或 synthdef（合成），二选一。"""
    synthdef: str | None = None
    params: dict = field(default_factory=dict)
    sample: str | None = None
    tune: bool = False


@dataclass(frozen=True)
class TriggerSpec:
    """即发即忘 voice。"""
    synthdef: str | None = None
    params: dict = field(default_factory=dict)
    sample: str | None = None
    tune: bool = False


@dataclass(frozen=True)
class GeneratorSpec:
    """间歇触发源：VoicePool.pump 按 interval 随机调度。"""
    interval: tuple[float, float]
    synthdef: str | None = None
    sample: str | None = None
    samples: tuple = ()
    freqs: tuple = ()
    params: dict = field(default_factory=dict)
    pan_random: bool = True


@dataclass
class MapResult:
    sustained: dict[VoiceKey, VoiceSpec] = field(default_factory=dict)
    generators: dict[VoiceKey, GeneratorSpec] = field(default_factory=dict)
    triggers: list[TriggerSpec] = field(default_factory=list)


class Mapper(Protocol):
    def map(self, state: State, events: Events) -> MapResult: ...


# ── KyotoMapper ──────────────────────────────────────────────────────────────

class KyotoMapper:
    """《京都岚山》映射：从 sonification/soundmat/mapping/kyoto.py 迁移。"""

    def __init__(self, manifest: dict):
        self.defaults = manifest.get("defaults", {})
        self.samples = manifest.get("samples", {})
        self.rings = manifest.get("rings", {})

    def map(self, state: State, events: Events) -> MapResult:
        return MapResult(
            sustained=self._sustained(state),
            generators=self._generators(state),
            triggers=self._triggers(events),
        )

    def _active_roles(self, state: State, mode: str):
        """遍历有石头的环中、指定 mode 的 (ring, role, cfg, count)。"""
        for ring_str, roles in self.rings.items():
            ring = int(ring_str)
            count = state.ring_count[ring]
            if count <= 0:
                continue
            for role, cfg in roles.items():
                if cfg.get("mode") == mode:
                    yield ring, role, cfg, count

    def _sustained(self, state: State) -> dict:
        out: dict = {}
        for ring, role, cfg, count in self._active_roles(state, "sustained"):
            if cfg.get("synthdef"):
                out[(ring, role)] = VoiceSpec(synthdef=cfg["synthdef"], params=_params(cfg))
            else:
                sample, tier = _pick_tier(cfg, count)
                params = _params(self.defaults, self.samples.get(sample), cfg, tier)
                params.setdefault("pan", 0.0)
                out[(ring, role)] = VoiceSpec(
                    sample=sample, params=params, tune=cfg.get("tune", False))
        return out

    def _generators(self, state: State) -> dict:
        out: dict = {}
        for ring, role, cfg, count in self._active_roles(state, "generator"):
            interval = tuple(cfg.get("interval", [4.0, 7.0]))
            if cfg.get("synthdef"):
                out[(ring, role)] = GeneratorSpec(
                    interval=interval,
                    synthdef=cfg["synthdef"],
                    freqs=tuple(_scale_freqs()),
                    params=_params(cfg),
                )
            else:
                out[(ring, role)] = GeneratorSpec(
                    interval=interval,
                    samples=tuple(cfg["samples"]),
                    params=_params(self.defaults, cfg),
                )
        return out

    def _triggers(self, events: Events) -> list:
        out = []
        for ring, sector in events.placed:
            for role, cfg in self.rings.get(str(ring), {}).items():
                if cfg.get("mode") != "trigger":
                    continue
                if cfg.get("synthdef"):
                    params = _params(cfg)
                    params["freq"] = _slice_freq(sector, config.NUM_SLICES)
                    params["pan"] = _pan(sector, config.NUM_SLICES)
                    out.append(TriggerSpec(synthdef=cfg["synthdef"], params=params))
                else:
                    sample = random.choice(cfg["samples"])
                    params = _params(self.defaults, self.samples.get(sample), cfg)
                    params["pan"] = _pan(sector, config.NUM_SLICES)
                    out.append(TriggerSpec(
                        sample=sample, params=params, tune=cfg.get("tune", False)))
        return out
