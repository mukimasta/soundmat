"""EventEngine：旋律 + bass，响应扫描线扫中石头（设计文档 §5 / JAM_DESIGN §5）。

每帧比较扫描角 prev→curr，过某石所在（合并后）扇区中心则命中。同一石 100ms 内不重复触发。
一帧内按合并扇区分组，组内 N 颗石头共享力度系数 1/√N（下限 0.2），避免多 Ring 同 slice
同时满力度叠满。命中后查触发表（chord × ring × 八分位）得级数 token，交桥层解析成 freq。

Burst（前向连发）按设计已废除，恒单音。
"""
from __future__ import annotations

import math

from ..scheduler.song_position import SongPositionTracker
from ..scheduler.timing import (
    SECTOR_RADIANS,
    Timing,
    normalize_angle,
    sector_center_angle,
    sweep_crossed_angle,
)
from ..ring_config import RingConfig
from ..theory.tonality import Tonality
from ..types import NoteEvent

MIN_RETRIGGER_SEC = 0.1


def _crossed_center_this_frame(prev_angle: float, curr_angle: float, target: float) -> bool:
    """把扫描弧切成 ≤半扇区的子步，逐段判断是否跨过 target，避免快扫漏命中。"""
    prev = normalize_angle(prev_angle)
    curr = normalize_angle(curr_angle)
    delta = curr - prev
    if delta < 0:
        delta += 2 * math.pi
    steps = max(1, math.ceil(delta / (SECTOR_RADIANS * 0.5)))
    for s in range(1, steps + 1):
        seg_prev = normalize_angle(prev + delta * (s - 1) / steps)
        seg_curr = normalize_angle(prev + delta * s / steps)
        if sweep_crossed_angle(seg_prev, seg_curr, target):
            return True
    return False


class EventEngine:
    def __init__(
        self,
        timing: Timing,
        ring_configs: dict[int, RingConfig],
        trigger_tables: dict[str, dict[int, list]],
        song_pos: SongPositionTracker,
    ):
        self.timing = timing
        self.ring_configs = ring_configs
        self.trigger_tables = trigger_tables   # symbol -> {ring -> [8 tokens]}
        self.song_pos = song_pos
        self._last_triggered: dict[tuple[int, int], float] = {}
        trigger_rings = [r for r, c in ring_configs.items() if c.is_trigger]
        self.min_trigger_ring = min(trigger_rings) if trigger_rings else 99
        self.max_trigger_ring = max(trigger_rings) if trigger_rings else -1

    def reset(self) -> None:
        self._last_triggered.clear()

    def set_timing(self, timing: Timing) -> None:
        self.timing = timing

    # ── token 查找 ──
    def _token_at(self, ring: int, chord_index: int, eighth_in_bar: int) -> str | None:
        prog = self.song_pos.progression
        if not (0 <= chord_index < len(prog)):
            return None
        symbol = prog[chord_index][0]
        ring_rows = self.trigger_tables.get(symbol)
        if not ring_rows:
            return None
        row = ring_rows.get(ring)
        if not row or eighth_in_bar >= len(row):
            return None
        return row[eighth_in_bar]

    def _sustain_for(self, cfg: RingConfig, sec_per_quarter: float | None) -> float:
        """旋律环：固定 note_sec gate。bass 环：四分音符 + tail（web bassTailSec，bpm 驱动）。"""
        if cfg.role == "bass" and sec_per_quarter is not None:
            return sec_per_quarter + cfg.tail_sec
        return cfg.note_sec

    def _note_for(self, ring: int, sector: int, loop_rotation: int,
                  tonality: Tonality, velocity: float,
                  sec_per_quarter: float | None = None) -> NoteEvent | None:
        pos = self.timing.resolve_position(sector, loop_rotation)
        token = self._token_at(ring, pos["chord_index"], pos["eighth_in_bar"])
        freq_ok = tonality.freq(token)
        if freq_ok is None:
            return None
        cfg = self.ring_configs[ring]
        return NoteEvent(
            ring=ring,
            degree=token,
            velocity=max(0.2, min(1.0, velocity)),
            sustain=self._sustain_for(cfg, sec_per_quarter),
            pan=0.0,
            source_slice=sector,
        )

    # ── 扫描命中 ──
    def emit_sweep(
        self,
        prev_angle: float,
        curr_angle: float,
        did_wrap: bool,
        occupied: set[tuple[int, int]],
        now: float,
        loop_rotation: int,
        tonality: Tonality,
        sec_per_quarter: float | None = None,
    ) -> list[NoteEvent]:
        # 1) 找命中石（在触发环、过合并扇区中心、未冷却）
        hits: list[tuple[int, int]] = []
        for ring, slc in occupied:
            cfg = self.ring_configs.get(ring)
            if cfg is None or not cfg.is_trigger:
                continue
            trigger_sector = self.timing.melody_trigger_sector(slc, True)
            target = sector_center_angle(trigger_sector)
            if not _crossed_center_this_frame(prev_angle, curr_angle, target):
                continue
            if now - self._last_triggered.get((ring, slc), 0.0) < MIN_RETRIGGER_SEC:
                continue
            hits.append((ring, slc))

        if not hits:
            return []

        # 2) 按合并扇区分组，组内共享 1/√N 力度
        groups: dict[int, list[tuple[int, int]]] = {}
        for ring, slc in hits:
            merged = self.timing.melody_trigger_sector(slc, True)
            groups.setdefault(merged, []).append((ring, slc))

        events: list[NoteEvent] = []
        for group in groups.values():
            vel_scale = 1.0 / math.sqrt(len(group)) if len(group) > 1 else 1.0
            for ring, slc in group:
                rot = self.timing.effective_loop_rotation(slc, loop_rotation, did_wrap)
                note = self._note_for(ring, slc, rot, tonality, vel_scale, sec_per_quarter)
                self._last_triggered[(ring, slc)] = now
                if note is not None:
                    events.append(note)
        return events

    # ── 空闲预览（control 0 时放石，单音）──
    def preview(self, ring: int, slc: int, loop_rotation: int, tonality: Tonality,
                sec_per_quarter: float | None = None) -> NoteEvent | None:
        cfg = self.ring_configs.get(ring)
        if cfg is None or not cfg.is_trigger:
            return None
        return self._note_for(ring, slc, loop_rotation, tonality, 1.0, sec_per_quarter)
