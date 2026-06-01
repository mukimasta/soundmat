"""VoicePool：reconcile 引擎 + 间歇触发调度器。

消费 mapper 的 MapResult：
  sustained  → 帧间 diff，起停调参（持续 voice，含采样和合成）
  generators → 间歇触发源，按 key 起停；pump(now) 按随机间隔发声
  triggers   → 本帧即发即忘

从 sonification/soundmat/audio/voices.py 迁移，改用 core.osc 接口。
buf/loop/out/revBus 等结构性参数在这里补。
"""
from __future__ import annotations

import random

from .. import config
from ..core.osc import ADD_TO_HEAD, OSCClient
from .mapping import GeneratorSpec, MapResult, TriggerSpec, VoiceKey, VoiceSpec

# ambient 总线（与 \master / \reverb synthdef 默认参数对齐）
_MIX_BUS = 2      # master 的 in=；sources 干声输出到这里
_REVERB_BUS = config.REVERB_BUS  # reverb aux 送（=8）


class VoicePool:
    def __init__(self, osc: OSCClient, group: int, buffers=None):
        self.osc = osc
        self.group = group
        self.buffers = buffers           # BufferPool | None
        self._nodes: dict[VoiceKey, int] = {}
        self._specs: dict[VoiceKey, VoiceSpec] = {}
        self._generators: dict[VoiceKey, dict] = {}   # {"spec": GeneratorSpec, "next": float|None}

    def reconcile(self, result: MapResult) -> None:
        self._reconcile_sustained(result.sustained)
        self._reconcile_generators(result.generators)
        for trig in result.triggers:
            self._fire(trig)

    def pump(self, now: float) -> None:
        """按时间推进间歇源，发到点的触发。每帧调用。"""
        for g in self._generators.values():
            if g["next"] is None:
                g["next"] = now + random.uniform(*g["spec"].interval)
            elif now >= g["next"]:
                self._fire(self._gen_trigger(g["spec"]))
                g["next"] = now + random.uniform(*g["spec"].interval)

    # ── 持续 voice ────────────────────────────────────────────────────────

    def _reconcile_sustained(self, desired: dict[VoiceKey, VoiceSpec]) -> None:
        for key in list(self._nodes):
            if key not in desired:
                self.osc.set_node(self._nodes[key], gate=0)
                del self._nodes[key]
                self._specs.pop(key, None)
        for key, spec in desired.items():
            if key not in self._nodes:
                self._nodes[key] = self._start(spec, loop=1)
                self._specs[key] = spec
            else:
                old = self._specs.get(key)
                if old is None or spec.sample != old.sample or spec.synthdef != old.synthdef:
                    self.osc.set_node(self._nodes[key], gate=0)
                    self._nodes[key] = self._start(spec, loop=1)
                elif spec.params != old.params:
                    self.osc.set_node(self._nodes[key], **spec.params)
                self._specs[key] = spec

    # ── 间歇触发源 ────────────────────────────────────────────────────────

    def _reconcile_generators(self, desired: dict[VoiceKey, GeneratorSpec]) -> None:
        for key in list(self._generators):
            if key not in desired:
                del self._generators[key]
        for key, spec in desired.items():
            if key in self._generators:
                self._generators[key]["spec"] = spec
            else:
                self._generators[key] = {"spec": spec, "next": None}

    def _gen_trigger(self, spec: GeneratorSpec) -> TriggerSpec:
        params = dict(spec.params)
        if spec.pan_random:
            params["pan"] = random.uniform(-1, 1)
        if spec.synthdef:
            if spec.freqs:
                params["freq"] = random.choice(spec.freqs)
            return TriggerSpec(synthdef=spec.synthdef, params=params)
        sample = random.choice(spec.samples)
        return TriggerSpec(sample=sample, params=params)

    # ── 起声 ─────────────────────────────────────────────────────────────

    def _fire(self, trig: TriggerSpec) -> None:
        self._start(trig, loop=0)

    def _start(self, spec, loop: int = 1) -> int:
        if spec.sample is not None:
            tune = getattr(spec, "tune", False)
            synthdef = (spec.synthdef
                        or (self.buffers.synthdef_for(spec.sample, tune=tune) if self.buffers else "playMono"))
            buf = self.buffers.get(spec.sample) if self.buffers else None
            params = self._strip_wrong_pan(synthdef, dict(spec.params))
            params.update(loop=loop, gate=1, out=_MIX_BUS, revBus=_REVERB_BUS)
            if buf is not None:
                params["buf"] = buf
            return self.osc.new_synth(synthdef, params, target=self.group, add_action=ADD_TO_HEAD)
        # 合成 voice：直出 MIX_BUS，不走 aux reverb
        params = dict(spec.params, gate=1, out=_MIX_BUS)
        return self.osc.new_synth(spec.synthdef, params, target=self.group, add_action=ADD_TO_HEAD)

    @staticmethod
    def _strip_wrong_pan(synthdef: str, params: dict) -> dict:
        """stereo def 用 width；mono def 用 pan。去掉另一个。"""
        params.pop("pan" if synthdef.startswith("playStereo") else "width", None)
        return params

    # ── 清理 ─────────────────────────────────────────────────────────────

    def free_all(self) -> None:
        for node_id in self._nodes.values():
            self.osc.set_node(node_id, gate=0)
        self._nodes.clear()
        self._specs.clear()
        self._generators.clear()
