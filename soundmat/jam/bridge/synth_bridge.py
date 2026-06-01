"""SynthBridge：NoteEvent / ChordEvent → OSC（/s_new）。

在此处应用 ring → instrument 映射、ring 增益、级数 → freq 解析。所有 synth 都 spawn 在
模式的 SC group 下；模式停止时一次 free_group 杀光。

总线（config）：旋律/bass → MELODY_BUS；和声 pad → HARMONY_BUS；鼓 → DRUM_BUS。
master synth 读这三条总线做总线增益 + Lo-Fi LPF/磁带饱和（见 master_fx）。
"""
from __future__ import annotations

from ... import config
from ...core.osc import ADD_TO_HEAD, OSCClient
from ..ring_config import RingConfig
from ..theory.tonality import Tonality
from ..types import ChordEvent, NoteEvent

# 鼓声部 → SynthDef 名
DRUM_SYNTHS = {"kick": "jam_kick", "snare": "jam_snare", "hihat": "jam_hihat"}


class SynthBridge:
    def __init__(
        self,
        osc: OSCClient,
        group: int,
        ring_configs: dict[int, RingConfig],
        tonality: Tonality,
        *,
        chord_pad_synth: str = "jam_chord_pad",
        chord_pad_gain: float = 1.0,
    ):
        self.osc = osc
        self.group = group
        self.ring_configs = ring_configs
        self.tonality = tonality
        self.chord_pad_synth = chord_pad_synth
        self.chord_pad_gain = chord_pad_gain
        self._pad_nodes: list[int] = []

    def set_tonality(self, tonality: Tonality) -> None:
        self.tonality = tonality

    # ── 旋律 / bass / 鼓 ──
    def handle_note(self, ev: NoteEvent) -> None:
        if ev.is_drum:
            self._handle_drum(ev)
        else:
            self._handle_melodic(ev)

    def _handle_melodic(self, ev: NoteEvent) -> None:
        cfg = self.ring_configs.get(ev.ring)
        if cfg is None or cfg.instrument is None:
            return
        freq = self.tonality.freq(ev.degree)
        if freq is None or freq <= 0:
            return
        # velocity 与 ringGain 分开传：对应 web 的 trigger velocity + 环专用总线 Gain
        params = {
            "freq": float(freq),
            "velocity": float(ev.velocity),
            "ringGain": float(cfg.gain),
            "sustain": float(ev.sustain),
            "pan": float(ev.pan),
            "out": config.MELODY_BUS,
        }
        params.update(cfg.params)
        self.osc.new_synth(cfg.instrument, params, target=self.group, add_action=ADD_TO_HEAD)

    def _handle_drum(self, ev: NoteEvent) -> None:
        synth = DRUM_SYNTHS.get(ev.voice or "")
        if synth is None:
            return
        self.osc.new_synth(
            synth,
            {"amp": float(ev.velocity), "sustain": float(ev.sustain), "out": config.DRUM_BUS},
            target=self.group,
            add_action=ADD_TO_HEAD,
        )

    # ── 和声 pad ──
    def handle_chord(self, ev: ChordEvent) -> None:
        if ev.release_first:
            self._release_pad()
        freqs = self.tonality.freqs(ev.degrees)
        for f in freqs:
            node = self.osc.new_synth(
                self.chord_pad_synth,
                {
                    "freq": float(f),
                    "amp": float(self.chord_pad_gain),
                    "hold": float(ev.hold),
                    "gate": 1,
                    "out": config.HARMONY_BUS,
                },
                target=self.group,
                add_action=ADD_TO_HEAD,
            )
            self._pad_nodes.append(node)

    def _release_pad(self) -> None:
        for node in self._pad_nodes:
            self.osc.free_node(node)
        self._pad_nodes.clear()

    def handle(self, ev) -> None:
        if isinstance(ev, NoteEvent):
            self.handle_note(ev)
        elif isinstance(ev, ChordEvent):
            self.handle_chord(ev)
