"""EventEngine：旋律 + bass，响应扫描线扫中石头（设计文档 §5 / JAM_DESIGN §5）。

每帧比较扫描角 prev→curr，过某石所在（合并后）扇区中心则命中。同一石 100ms 内不重复触发。
一帧内按合并扇区分组，组内 N 颗石头共享力度系数 1/√N（下限 0.2），避免多 Ring 同 slice
同时满力度叠满。命中后查触发表（chord × ring × 八分位）得级数 token，交桥层解析成 freq。

实现：维护 `merged_sector → set[(ring, slc)]` 倒排索引（增量按 occupied 差集），
每帧只对**有石头**的合并扇区中心做角度跨越判断，不再 O(N) 扫所有占用格。

Burst（前向连发）按设计已废除，恒单音。
"""
from __future__ import annotations

import math

from ..scheduler.song_position import SongPositionTracker
from ..scheduler.timing import (
    SECTOR_COUNT,
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
        # 倒排索引：merged_sector → 触发环上的 {(ring, slc)}；按 occupied 差集增量维护
        self._merged_to_stones: dict[int, set[tuple[int, int]]] = {}
        self._last_occupied: set[tuple[int, int]] = set()
        self._build_merged_targets()

    def _build_merged_targets(self) -> None:
        """缓存所有可能的 merged sector 中心角，供扫描弧跨越查询。"""
        if self.timing.is_two_bar:
            sectors = list(range(0, SECTOR_COUNT, 2))
        else:
            sectors = list(range(SECTOR_COUNT))
        self._merged_targets: list[tuple[int, float]] = [
            (ms, sector_center_angle(ms)) for ms in sectors
        ]

    def _rebuild_index(self, occupied: set[tuple[int, int]]) -> None:
        self._merged_to_stones.clear()
        for ring, slc in occupied:
            cfg = self.ring_configs.get(ring)
            if cfg is None or not cfg.is_trigger:
                continue
            ms = self.timing.melody_trigger_sector(slc, True)
            self._merged_to_stones.setdefault(ms, set()).add((ring, slc))

    def _update_index(self, occupied: set[tuple[int, int]]) -> None:
        """按差集增量同步倒排索引。O(|added|+|removed|)。"""
        if occupied is self._last_occupied:
            return
        added = occupied - self._last_occupied
        removed = self._last_occupied - occupied
        if added or removed:
            for ring, slc in removed:
                cfg = self.ring_configs.get(ring)
                if cfg is None or not cfg.is_trigger:
                    continue
                ms = self.timing.melody_trigger_sector(slc, True)
                bucket = self._merged_to_stones.get(ms)
                if bucket is None:
                    continue
                bucket.discard((ring, slc))
                if not bucket:
                    del self._merged_to_stones[ms]
            for ring, slc in added:
                cfg = self.ring_configs.get(ring)
                if cfg is None or not cfg.is_trigger:
                    continue
                ms = self.timing.melody_trigger_sector(slc, True)
                self._merged_to_stones.setdefault(ms, set()).add((ring, slc))
        self._last_occupied = set(occupied)

    def reset(self) -> None:
        self._last_triggered.clear()
        self._merged_to_stones.clear()
        self._last_occupied = set()

    def mark_triggered(self, ring: int, slc: int, now: float) -> None:
        """记录已触发，避免与扫线命中重复（100ms 冷却）。"""
        self._last_triggered[(ring, slc)] = now

    def set_timing(self, timing: Timing) -> None:
        self.timing = timing
        self._build_merged_targets()
        prev = self._last_occupied
        self._merged_to_stones.clear()
        self._last_occupied = set()
        if prev:
            self._update_index(prev)

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
        """旋律环：固定 note_sec。bass：1×四分 + tail（web 单音 playTriggerBurst remaining=1）。"""
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
        # 同步倒排索引（差集，O(|added|+|removed|)；多数帧为 0）
        self._update_index(occupied)
        if not self._merged_to_stones:
            return []

        # 1) 用倒排索引按"扫描弧穿过的合并扇区中心"取候选；冷却仍按 (ring, slc) 过滤
        events: list[NoteEvent] = []
        for ms, target in self._merged_targets:
            stones = self._merged_to_stones.get(ms)
            if not stones:
                continue
            if not _crossed_center_this_frame(prev_angle, curr_angle, target):
                continue
            hits: list[tuple[int, int]] = []
            for ring, slc in stones:
                if now - self._last_triggered.get((ring, slc), 0.0) < MIN_RETRIGGER_SEC:
                    continue
                hits.append((ring, slc))
            if not hits:
                continue
            # 同 merged sector 即同组：共享 1/√N 力度
            vel_scale = 1.0 / math.sqrt(len(hits)) if len(hits) > 1 else 1.0
            for ring, slc in hits:
                rot = self.timing.effective_loop_rotation(slc, loop_rotation, did_wrap)
                note = self._note_for(ring, slc, rot, tonality, vel_scale, sec_per_quarter)
                self._last_triggered[(ring, slc)] = now
                if note is not None:
                    events.append(note)
        return events

    # ── 空闲预览（control 0 时放石，单音）──
    def preview(self, ring: int, slc: int, loop_rotation: int, tonality: Tonality,
                sec_per_quarter: float | None = None, *, velocity: float = 1.0) -> NoteEvent | None:
        cfg = self.ring_configs.get(ring)
        if cfg is None or not cfg.is_trigger:
            return None
        return self._note_for(ring, slc, loop_rotation, tonality, velocity, sec_per_quarter)
