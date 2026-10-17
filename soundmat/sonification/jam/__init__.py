"""Jam 模式：一首循环曲，扫描线经过石头时发声（SONIFICATION「Jam 模式的运行」）。

音乐逻辑移植自第一版 ``jam/``（理论、时间方案、曲式、扫描命中、灯光），输出改为意图：

- 走带：空闲 → 播放 → 曲终。控制区压力超过启动阈值时开始播放，音乐时间从零开始计；
  控制区压力消失超过保持时间后回到空闲并归零。曲式走完进入曲终，清空控制区后才能重新开始。
- Lo-Fi：控制区压力连续映射为 Lo-Fi 强度（平滑后），作为全局参数，不受走带状态影响。
- 播放中每一拍把前瞻时间窗换算成音乐时间区间，在区间内生成：每小节一个和声持续声部
  （标识含小节序号，带准确的开始时刻）、十六分网格上的鼓、扫描线经过石头的准确时刻的旋律与贝斯。
- 空闲时新放下的石头立即预听一声；播放中是否预听由编排决定。

编排格式见 docs/implementation/ARRANGEMENTS.md。
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field

from ...clock import Beat
from ...perception.model import MatEvent, MatSnapshot
from ...perception.zones import ZONES, ring_indices
from ..intent import BeatOutput, Event, LightIntent, ModeStatus, Position, SoundIntent, Source, Voice
from ..mode import LoadError, LoadPlan, Mode
from .lights import JamLights
from .theory import Tempo, Tonality, valid_token
from .timing import Timing

FULL_SCALE = 4095.0            # 编排里压力相关数值是 ADC 原始读数
MIN_RETRIGGER = 0.1            # 同一颗石头 100 ms 内不重复触发（预听后紧接着被扫到）
GHOST_VELOCITY = 0.38
LOFI_ALPHA_UP = 0.38           # Lo-Fi 平滑（每拍一次，与第一版 60 Hz 主循环一致）
LOFI_ALPHA_DOWN = 0.68
DRUM_VOICES = ("kick", "snare", "hihat")
# 声部超出预算时：和声与鼓高于贝斯，贝斯高于旋律
PRIORITY = {"harmony": 3, "drums": 3, "bass": 2, "melody": 1}


@dataclass
class RingRole:
    ring: int
    role: str                  # bass / melody
    instrument: str
    note_sec: float = 0.5
    tail_sec: float = 0.0
    gain: float = 1.0
    params: dict = field(default_factory=dict)


def _interp(points: list[tuple[float, float]], x: float) -> float:
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (0.0 if x1 == x0 else (x - x0) / (x1 - x0))
    return points[-1][1]


def _fmt(sec: float) -> str:
    s = max(0, int(sec))
    return f"{s // 60}:{s % 60:02d}"


class JamMode(Mode):
    name = "jam"

    # ── 加载 ────────────────────────────────────────────────────────────

    def load(self) -> LoadPlan:
        c = self.arrangement.content
        music = c.get("music", {})
        try:
            self.tempo = Tempo(float(music.get("bpm", 120)))
            self.tonality = Tonality(music.get("key", "C"), music.get("scale", "major"))
            self.timing = Timing(int(music.get("scheme", 2)))
        except (ValueError, TypeError) as e:
            raise LoadError(str(e)) from e
        self.lookahead = float(music.get("lookahead", 0.1))

        ctrl = c.get("control", {})
        self.control_rings = tuple(ctrl.get("rings", (0, 1)))
        self.start_threshold = float(ctrl.get("start_threshold", 250)) / FULL_SCALE
        self.release_hold = float(ctrl.get("release_hold", 0.1))
        lo, hi = ctrl.get("lofi_range", (1000, 8000))
        self.lofi_lo, self.lofi_hi = float(lo) / FULL_SCALE, float(hi) / FULL_SCALE
        self.preview_idle = float(ctrl.get("preview_idle", 0.5))
        self.preview_playing = float(ctrl.get("preview_playing", 0.0))

        lofi = c.get("lofi", {})
        self.lofi_curves = {}
        for name in ("cutoff", "drive", "gain"):
            pts = sorted((float(a), float(b)) for a, b in lofi.get(name, ()))
            if not pts:
                raise LoadError(f"lofi.{name} 不能为空")
            self.lofi_curves[name] = pts

        self.progression: list[tuple[str, int]] = []
        self.voicings: dict[str, list[str]] = {}
        for entry in c.get("progression", []):
            cid, bars = entry["id"], int(entry.get("bars", 1))
            self.progression.append((cid, bars))
            self.voicings[cid] = list(entry.get("voicing", []))
        if not self.progression:
            raise LoadError("progression 不能为空")
        self.cycle_bars = sum(b for _, b in self.progression)
        self.bar_chord: list[int] = []
        for idx, (_, bars) in enumerate(self.progression):
            self.bar_chord += [idx] * bars

        self.rings: dict[int, RingRole] = {}
        reserved = {"role", "instrument", "note_sec", "tail_sec", "gain"}
        for key, cfg in c.get("rings", {}).items():
            ring = int(key)
            role = cfg.get("role")
            if role not in ("bass", "melody"):
                raise LoadError(f"第 {ring} 环：role 应为 bass 或 melody")
            if ring in self.control_rings:
                raise LoadError(f"第 {ring} 环是控制区，不能同时是触发环")
            if not cfg.get("instrument"):
                raise LoadError(f"第 {ring} 环缺少 instrument")
            self.rings[ring] = RingRole(
                ring=ring, role=role, instrument=cfg["instrument"],
                note_sec=float(cfg.get("note_sec", 0.5)), tail_sec=float(cfg.get("tail_sec", 0.0)),
                gain=float(cfg.get("gain", 1.0)),
                params={k: float(v) for k, v in cfg.items() if k not in reserved},
            )

        self.triggers: dict[str, dict[int, list]] = {}
        for cid, rows in c.get("triggers", {}).items():
            self.triggers[cid] = {}
            for rkey, row in rows.items():
                ring = int(rkey)
                if len(row) != 8:
                    raise LoadError(f"触发表 {cid} 第 {ring} 环应有 8 个八分位")
                for tok in row:
                    if not valid_token(tok):
                        raise LoadError(f"触发表 {cid} 第 {ring} 环有无法识别的音级 {tok}")
                self.triggers[cid][ring] = list(row)
        for cid, voicing in self.voicings.items():
            for tok in voicing:
                if not valid_token(tok):
                    raise LoadError(f"和弦 {cid} 的配音有无法识别的音级 {tok}")

        drums = c.get("drums", {})
        self.patterns = drums.get("patterns", {})
        self.sequence = list(drums.get("sequence", []))
        if not self.sequence:
            raise LoadError("drums.sequence 不能为空")
        for name in self.sequence:
            if name not in self.patterns:
                raise LoadError(f"鼓的曲式引用了不存在的段落 {name}")
        self.bars_per_section = self.timing.bars_per_harmony_cycle
        self.total_bars = len(self.sequence) * self.bars_per_section
        self.form_duration = self.total_bars * self.tempo.bar

        inst = c.get("instruments", {})
        self.pad_instrument = inst.get("pad", "jam_chord_pad")
        self.drum_instruments = {v: inst.get(v, f"jam_{v}") for v in DRUM_VOICES}
        self.mix = {f"bus.{k}": float(v) for k, v in c.get("mix", {}).items()}

        instruments = {self.pad_instrument, *self.drum_instruments.values(), *(r.instrument for r in self.rings.values())}
        control = frozenset(i for r in self.control_rings for i in ring_indices(r))
        return LoadPlan(
            instruments=frozenset(instruments), control_zones=control, lookahead=self.lookahead,
            buses=tuple(f"ring{r}" for r in range(8)) + ("harmony", "drums"),
        )

    # ── 运行 ────────────────────────────────────────────────────────────

    def start(self, t: float) -> None:
        self.prefix = f"{self.arrangement.id}.{uuid.uuid4().hex[:6]}"
        self.state = "idle"
        self.run = 0
        self.start_t = 0.0
        self.scheduled = 0.0             # 已经排到的音乐时间
        self.inactive_since: float | None = None
        self.lofi = None
        self.last_trigger: dict[int, float] = {}
        self.lights = JamLights(self.ctx.led_count)
        self.preview_n = 0

    def tick(self, beat: Beat, snapshot: MatSnapshot, events: list[MatEvent]) -> BeatOutput:
        t = beat.t
        st = snapshot.state
        pressure = st.control_pressure or 0.0
        active = self._control_active(pressure >= self.start_threshold, t)

        if not active:
            if self.state != "idle":
                self.state = "idle"
                self.scheduled = 0.0
                self.last_trigger.clear()
        elif self.state == "idle":
            self.state = "playing"
            self.run += 1
            self.start_t = t
            self.scheduled = 0.0

        out_events: list[Event] = []
        voices: list[Voice] = []
        trigger_stones = [(ZONES[z].ring, ZONES[z].slot, z) for z in st.occupied if ZONES[z].ring in self.rings]

        if self.state == "playing":
            mt_now = t - self.start_t
            mt_end = min(t + self.lookahead - self.start_t, self.form_duration)
            if mt_end > self.scheduled:
                out_events += self._drums(self.scheduled, mt_end)
                out_events += self._scan(self.scheduled, mt_end, trigger_stones)
                self.scheduled = mt_end
            voices += self._harmony(mt_now, mt_end)
            if mt_now >= self.form_duration:
                self.state = "ended"

        placed = [e for e in events if e.kind == "place" and ZONES[e.zone].ring in self.rings]
        vel = self.preview_idle if self.state == "idle" else self.preview_playing if self.state == "playing" else 0.0
        if vel > 0:
            for e in placed:
                ev = self._preview(e.zone, t, vel)
                if ev is not None:
                    out_events.append(ev)

        lofi = self._lofi_step(pressure)
        globals_ = {
            "cutoff": round(_interp(self.lofi_curves["cutoff"], lofi), 1),
            "drive": round(_interp(self.lofi_curves["drive"], lofi), 5),
            "lofiGain": round(_interp(self.lofi_curves["gain"], lofi), 3),
            **self.mix,
        }

        sweep = self.timing.sweep_position(max(0.0, t - self.start_t), self.tempo.bpm) if self.state == "playing" else 0.0
        light = self.lights.render(t, state=self.state, sweep=sweep,
                                   stones=[(r, s) for r, s, _ in trigger_stones])
        return BeatOutput(
            sound=SoundIntent(tuple(voices), tuple(out_events), globals_),
            light=LightIntent((light,)),
            status=self._status(t, lofi),
        )

    def _control_active(self, raw: bool, t: float) -> bool:
        """控制区压力消失后保持 ``release_hold`` 秒再判定为松开，过滤读数闪断。"""
        if raw:
            self.inactive_since = None
            return True
        if self.state == "idle":
            return False
        if self.inactive_since is None:
            self.inactive_since = t
        return t - self.inactive_since < self.release_hold

    def _lofi_step(self, pressure: float) -> float:
        lo, hi = self.lofi_lo, self.lofi_hi
        target = 1000.0 if hi <= lo and pressure >= hi else max(0.0, min(1000.0, (pressure - lo) / (hi - lo) * 1000.0))
        if self.lofi is None:
            self.lofi = target
        else:
            a = LOFI_ALPHA_DOWN if target < self.lofi else LOFI_ALPHA_UP
            nxt = self.lofi + (target - self.lofi) * a
            if target <= 0.0 and nxt < 1.5:
                nxt = 0.0
            if target >= 999.0 and nxt > 998.5:
                nxt = 1000.0
            self.lofi = max(0.0, min(1000.0, nxt))
        return self.lofi

    # ── 和声、鼓、扫描 ──────────────────────────────────────────────────

    def _chord_for_bar(self, bar: int) -> str:
        return self.progression[self.bar_chord[bar % self.cycle_bars]][0]

    def _harmony(self, mt_now: float, mt_end: float) -> list[Voice]:
        """当前小节的和声，以及开始时刻已落在前瞻时间窗内的下一小节。"""
        out = []
        bar_len = self.tempo.bar
        first = int(mt_now // bar_len)
        last = int(max(mt_now, mt_end - 1e-9) // bar_len)
        for bar in range(first, last + 1):
            if bar >= self.total_bars:
                break
            freqs = self.tonality.freqs(self.voicings.get(self._chord_for_bar(bar), []))
            if not freqs:
                continue
            params = {f"freq{i}": (freqs[i] if i < len(freqs) else 0.0) for i in range(5)}
            params["amp"] = 1.0
            out.append(Voice(
                id=f"harmony.r{self.run}.bar{bar}", source=Source("instrument", self.pad_instrument),
                bus="harmony", params=params, fade_in=0.0, fade_out=1.5,
                priority=PRIORITY["harmony"], start=self.start_t + bar * bar_len,
            ))
        return out

    def _drums(self, mt0: float, mt1: float) -> list[Event]:
        out = []
        tp = self.tempo
        for i in tp.sixteenths_in(mt0, mt1):
            bar, step = divmod(i, 16)
            if bar >= self.total_bars:
                continue
            section = self.sequence[(bar // self.bars_per_section) % len(self.sequence)]
            pattern = self.patterns[section]
            for voice in DRUM_VOICES:
                row = pattern.get(voice) or []
                level = row[step] if step < len(row) else 0
                if not level:
                    continue
                sustain = tp.eighth
                if voice == "hihat":
                    sustain = tp.sixteenth / (4.0 if level == 2 else 2.0)
                out.append(Event(
                    id=f"{self.prefix}.r{self.run}.{voice}.{i}", time=self.start_t + i * tp.sixteenth,
                    source=Source("instrument", self.drum_instruments[voice]), bus="drums",
                    params={"amp": GHOST_VELOCITY if level == 2 else 1.0, "sustain": sustain},
                    priority=PRIORITY["drums"],
                ))
        return out

    def _scan(self, mt0: float, mt1: float, stones: list[tuple[int, int, int]]) -> list[Event]:
        if not stones:
            return []
        groups: dict[int, list[tuple[int, int, int]]] = {}
        for ring, slot, z in stones:
            groups.setdefault(self.timing.trigger_sector(slot), []).append((ring, slot, z))
        out = []
        for mt, target, k in self.timing.hits_in(mt0, mt1, self.tempo.bpm, groups.keys()):
            t_hit = self.start_t + mt
            hits = [s for s in groups[target] if t_hit - self.last_trigger.get(s[2], -1e9) >= MIN_RETRIGGER]
            if not hits:
                continue
            scale = 1.0 / math.sqrt(len(hits)) if len(hits) > 1 else 1.0
            rotation = k % 4 if self.timing.is_two_bar else 0
            for ring, slot, z in hits:
                self.last_trigger[z] = t_hit
                ev = self._note(ring, slot, z, rotation, scale, t_hit,
                                f"{self.prefix}.r{self.run}.scan.{z}.{k}")
                if ev is not None:
                    out.append(ev)
                    self.lights.flash(t_hit, slot, ring)
        return out

    def _preview(self, zone: int, t: float, velocity: float) -> Event | None:
        z = ZONES[zone]
        rotation = 0
        if self.state == "playing" and self.timing.is_two_bar:
            k = int(self.timing.sweep_position(t - self.start_t, self.tempo.bpm) // 32)
            rotation = k % 4
        self.preview_n += 1
        ev = self._note(z.ring, z.slot, zone, rotation, velocity, t, f"{self.prefix}.preview.{self.preview_n}")
        if ev is not None:
            self.lights.preview(t, z.slot, z.ring)
            if self.state == "playing":
                self.last_trigger[zone] = t
        return ev

    def _note(self, ring: int, slot: int, zone: int, rotation: int, velocity: float,
              t: float, eid: str) -> Event | None:
        role = self.rings[ring]
        chord_idx, eighth = self.timing.resolve(slot, rotation)
        if not 0 <= chord_idx < len(self.progression):
            return None
        row = self.triggers.get(self.progression[chord_idx][0], {}).get(ring)
        if not row:
            return None
        freq = self.tonality.freq(row[eighth])
        if freq is None:
            return None
        sustain = self.tempo.quarter + role.tail_sec if role.role == "bass" else role.note_sec
        z = ZONES[zone]
        return Event(
            id=eid, time=t, source=Source("instrument", role.instrument), bus=f"ring{ring}",
            params={"freq": freq, "velocity": max(0.2, min(1.0, velocity)), "ringGain": role.gain,
                    "sustain": sustain, **role.params},
            position=Position(z.center_deg, z.radius), priority=PRIORITY[role.role], category="melodic",
        )

    # ── 状态 ────────────────────────────────────────────────────────────

    def _status(self, t: float, lofi: float) -> ModeStatus:
        if self.state == "idle":
            return ModeStatus("空闲 · 压住中间两环开始", "Lo-Fi —", "idle")
        if self.state == "ended":
            return ModeStatus("曲终 · 清空中间两环，再压一次重新开始", "", "ended")
        mt = max(0.0, t - self.start_t)
        bar = int(mt // self.tempo.bar)
        sec = min(bar // self.bars_per_section, len(self.sequence) - 1)
        text = f"第 {sec + 1} 段 {self.sequence[sec]} · {_fmt(mt)} / {_fmt(self.form_duration)}"
        return ModeStatus(text, f"Lo-Fi {round(lofi / 10)}%", "playing")
