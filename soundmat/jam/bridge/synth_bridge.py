"""SynthBridge：NoteEvent / ChordEvent → OSC（/s_new）。

在此处应用 ring → instrument 映射、ring 增益、级数 → freq 解析。所有 synth 都 spawn 在
模式的 SC group 下；模式停止时一次 free_group 杀光。

总线（config）：旋律/bass → MELODY_BUS；和声 pad → HARMONY_BUS；鼓 → DRUM_BUS。
master synth 读这三条总线做总线增益 + Lo-Fi LPF/磁带饱和（见 master_fx）。

复音管理：melody/bass voice FIFO 队列；超过 ``JAM_MAX_MELODIC_VOICES`` 时新 voice spawn
前 free 最老的（"voice stealing"）。pad/鼓不限。SC 端 EnvGen doneAction:2 仍负责自然结束；
为避免对已自然结束的 node 发 /n_free 触发 server warning，deque 里同时记录预计死亡时刻
（spawn 时间 + sustain + release buffer），过期的直接出队不下发 /n_free。
"""
from __future__ import annotations

import time
from collections import deque

from ... import config
from ...core.osc import ADD_TO_HEAD, OSCClient
from ..ring_config import RingConfig
from ..theory.tonality import Tonality
from ..types import ChordEvent, NoteEvent

# 鼓声部 → SynthDef 名
DRUM_SYNTHS = {"kick": "jam_kick", "snare": "jam_snare", "hihat": "jam_hihat"}

# jam_chord_pad 多通道版本接受 5 路 freq；progression voicing 即 5 音
CHORD_PAD_VOICES = 5

# 各 instrument 的 envelope 总时长（与 SynthDef 内 EnvGen 同步，超出 → doneAction:2 自然 free）。
# 用于估算 expected_done_at：cap 触发时已自然死亡的 voice 不发 /n_free，避免 server warning。
# - "fixed"  : envelope 总长 = 这个固定秒数（不依赖 sustain；如 marimba 的 jamToneExpDecay）
# - "sustain": envelope 总长 = sustain + 这个 release 余量（如 rhodes 的 jamGateReleaseEnv）
_INSTRUMENT_ENVELOPE = {
    # marimba: jamToneExpDecay(0.012, 2.0) → 2.012s 固定；sustain 输入对 envelope 无影响
    "jam_marimba":   ("fixed",   2.05),
    # rhodes: atk+dec+hold(=sustain-atk-dec)+rel = sustain + rel(0.85~0.9)
    "jam_rhodes":    ("sustain", 1.0),
    # pad_pluck: atk+dec+aHold+rel = sustain + rel(0.8)
    "jam_pad_pluck": ("sustain", 0.85),
    # pluck_bass: gate-style envelope，rel ≈ 0.4
    "jam_pluck_bass": ("sustain", 0.5),
    # sub_bass: rel = 0.34
    "jam_sub_bass":  ("sustain", 0.4),
}
_DEFAULT_RELEASE_SEC = 0.5


def _voice_done_at(instrument: str, sustain: float, now: float) -> float:
    """估算 voice 自然 doneAction:2 释放的 monotonic 时刻。"""
    spec = _INSTRUMENT_ENVELOPE.get(instrument)
    if spec is None:
        return now + float(sustain) + _DEFAULT_RELEASE_SEC
    kind, value = spec
    if kind == "fixed":
        return now + float(value)
    return now + float(sustain) + float(value)


class SynthBridge:
    def __init__(
        self,
        osc: OSCClient,
        group: int,
        ring_configs: dict[int, RingConfig],
        tonality: Tonality,
        *,
        harmony_group: int | None = None,
        chord_pad_synth: str = "jam_chord_pad",
        chord_pad_gain: float = 1.0,
    ):
        self.osc = osc
        self.group = group
        self.harmony_group = harmony_group if harmony_group is not None else group
        self.ring_configs = ring_configs
        self.tonality = tonality
        self.chord_pad_synth = chord_pad_synth
        self.chord_pad_gain = chord_pad_gain
        # FIFO 队列记录已 spawn 的 melody/bass voice：(node_id, expected_done_at_monotonic)
        # 复音上限触发时只对"还应该活着"的 node 发 /n_free，避免给已自然结束的发命令
        self._melodic_voices: deque[tuple[int, float]] = deque()

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
        now = time.monotonic()
        # 复音上限：先释放最老（"voice stealing"），再 spawn 新 voice
        self._enforce_voice_cap(now)
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
        node_id = self.osc.new_synth(cfg.instrument, params, target=self.group, add_action=ADD_TO_HEAD)
        done_at = _voice_done_at(cfg.instrument, ev.sustain, now)
        self._melodic_voices.append((node_id, done_at))

    def _enforce_voice_cap(self, now: float) -> None:
        """超过 config.JAM_MAX_MELODIC_VOICES（>0）时 free 最老 melodic voice。

        队列里 done_at 已过期的 voice 视为已自然结束，仅出队不发 /n_free（避免 server warning）。
        """
        cap = int(config.JAM_MAX_MELODIC_VOICES)
        if cap <= 0:
            return
        # 先清理队头自然过期的，看是否已腾出位置
        while self._melodic_voices and self._melodic_voices[0][1] <= now:
            self._melodic_voices.popleft()
        # 仍超过 cap → 真正 stealing：剩下的还应该活着，发 /n_free
        while len(self._melodic_voices) >= cap:
            old_id, _done_at = self._melodic_voices.popleft()
            try:
                self.osc.free_node(old_id)
            except Exception:
                pass

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
        # web releaseAll + 新和弦：旧 pad 靠包络 release 淡出，不逐个 free_node
        # 多频点合并：原 N voice = N 个 SynthDef 实例 → 1 个实例 + N 路 freq（共享 envelope/LPF/vibrato）
        freqs = self.tonality.freqs(ev.degrees)
        if not freqs:
            return
        params: dict = {
            "amp": float(self.chord_pad_gain),
            "hold": float(ev.hold),
            "out": config.HARMONY_BUS,
        }
        for i in range(CHORD_PAD_VOICES):
            params[f"freq{i}"] = float(freqs[i]) if i < len(freqs) else 0.0
        self.osc.new_synth(
            self.chord_pad_synth,
            params,
            target=self.harmony_group,
            add_action=ADD_TO_HEAD,
        )

    def _release_pad(self) -> None:
        # pad 包络结束会 doneAction:2 自毁；勿对历史 node id 发 /n_free（会报 not found）
        self.osc.deep_free_group(self.harmony_group)

    def handle(self, ev) -> None:
        if isinstance(ev, NoteEvent):
            self.handle_note(ev)
        elif isinstance(ev, ChordEvent):
            self.handle_chord(ev)
