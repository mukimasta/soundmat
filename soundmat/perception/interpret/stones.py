"""石头跟踪：直接从压力图找出石头，跨帧对上号，给出放下、拿起和挪动（DATA_MODEL「垫面状态」）。

一颗石头可以压到几个区（骑在分界线上，或者正在滑过去）。先按区各自判断有没有石头再归并，骑在线上的
石头两边可能都不到阈值、直接被丢掉；所以这里不按区判断，而是把压力连成块、按石头判断。读数都换算成
"几个放下阈值"（u = 读数 / 这个区的放下阈值，内两环的阈值比外环低）。2026-10-20 的实测依据见
``docs/information/investigations/STONE_SENSING_20261020.md``。

每一帧：

1. 串扰补偿（只用于已有的石头）：同一根扇区导电条上别处有压力时，这根条上的读数会被明显拉低
   （实测平均掉到 0.43 倍），不会被抬高。已有石头的读数按 u × (1 + k × 这根条上其余读数之和) 补回来，
   这样它不会因为别处放了石头而被当成拿起。新出现的压力不补偿，以免把噪声放大成假石头。
2. 已有的石头先认领自己的区，再认领紧挨着的、有压力的区（同一个区够得着几颗时给最近的那颗）。
   相邻两帧之间石头跨不过一个区（控制器约 29 帧/秒），所以"有共用的区"就能对上号，不需要算距离匹配。
   暂时找不到的石头在隔一个区的范围里找回一块连着的压力：只认它消失之后才出现的（之前就在的是别的东西），
   而且要和它平时的压力相当（手碰一下不算）；最内环的石头可以穿过圆心（那里没有电极），整个最内环都算在范围里。
3. 一颗石头的范围里有区的压力新升到够一颗石头：原来的压力没有让出来，而且总压力比平时多出了一颗石头，
   就是旁边又放了一颗，分出去。滑过去时原来的压力会让出来，总压力大致不变。
4. 石头的主区是压力最大的区；别的区要比主区大出一截、并且保持一小段时间才换过去，换了就是挪动。
   真实游玩里常见两个区的读数一帧一帧地交替（石头在手里晃、被压着来回滚），不保持就会来回报挪动。
5. 一颗石头找不到压力一段时间才算拿起。刚动过的、或者消失之前压力已经在一帧帧往下掉的石头等得久一些：
   拖过分界线时，石头先慢慢滑离原来的区，有一两帧两边都读不到；真正拿起时压力几乎一下子掉到底
   （实测 96% 在一帧之内）。
6. 没被认领的压力连成块，作为候选；总压力够一颗石头并持续一段时间，才算放下。
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from ..model import MatEvent
from ..zones import NUM_ZONES, ZONES


def _adjacent(a, b) -> bool:
    """同环左右相邻，或相邻两环在角度上有重叠、角对角也算（石头可能正好压在四个区的交点上）。"""
    if a.index == b.index:
        return False
    d = abs((a.center_deg - b.center_deg + 180.0) % 360.0 - 180.0)
    if a.ring == b.ring:
        return d <= a.span_deg + 1e-6
    if abs(a.ring - b.ring) == 1:
        return d <= (a.span_deg + b.span_deg) / 2 + 1e-6
    return False


NEIGHBOURS: tuple[tuple[int, ...], ...] = tuple(
    tuple(b.index for b in ZONES if _adjacent(a, b)) for a in ZONES)
NEIGHBOURS2: tuple[tuple[int, ...], ...] = tuple(
    tuple(sorted({k for j in (i, *NEIGHBOURS[i]) for k in NEIGHBOURS[j]} - {i})) for i in range(NUM_ZONES))
_INNERMOST = frozenset(z.index for z in ZONES if z.ring == 0)

# 区域中心的平面坐标（控制台绘图单位；x 向右、y 向上，0° 在 12 点方向、顺时针）
_R = np.array([(z.r_inner + z.r_outer) / 2 for z in ZONES])
_A = np.radians([z.center_deg for z in ZONES])
_X = _R * np.sin(_A)
_Y = _R * np.cos(_A)

STRONG = 1.0       # 一个区的读数达到一个放下阈值，算"够一颗石头"
STRONG_OFF = 0.7   # 掉到这以下才不算（避免在 1 附近来回进出）


@dataclass(frozen=True)
class TrackerParams:
    place_threshold: np.ndarray      # 每个区的放下阈值（归一化压力），shape (224,)
    strips: np.ndarray               # 每个区所在的扇区导电条（接线扇区 0–31），串扰只沿同一根条发生
    floor: float = 0.4               # 一个区读数达到放下阈值的这么多倍，才算这颗石头的一部分
    place_strength: float = 1.0      # 候选的总压力（以放下阈值为单位）达到这么多才可能放下
    occupy_hold: float = 0.08        # 秒：总压力持续够了这么久才算放下
    release_hold: float = 0.08       # 秒：静止的石头找不到压力这么久才算拿起
    release_hold_moving: float = 0.4 # 秒：刚动过的石头等这么久（拖过分界线时两边会短暂都读不到）
    center_hold: float = 1.0         # 秒：最内环刚动过的石头等这么久（穿过圆心没有电极的那一块）
    moving_window: float = 0.8       # 秒：主区换过、或有区的压力新升到够一颗石头之后这么久之内，算"刚动过"
    crosstalk: float = 7.0           # 串扰补偿系数 k（实测拟合的中位数）
    anchor_switch: float = 1.15      # 别的区要比主区大这么多倍才换主区
    anchor_hold: float = 0.15        # 秒：并且保持这么久（原来的主区已经没有压力时立即换）
    split_gain: float = 1.0          # 新升起来的区总压力达到这么多（放下阈值为单位）才可能是另一颗石头
    split_core: float = 0.75         # 原来的压力保持在平时的这个比例以上，才算没有让出来
    split_window: float = 0.4        # 秒：区的压力升到够一颗石头之后这么久之内算"新升起来"
    split_hold: float = 0.15         # 秒：分出新石头的条件持续这么久才分（比放下长一点，给滑动留出让压力的时间）
    reacquire: float = 0.1           # 找回暂时找不到的石头时，那块压力至少是它平时总压力的这个比例
    fade_ratio: float = 0.75         # 总压力低于平时的这个比例，算"在往下掉"
    fade_min: float = 0.1            # 秒：消失之前已经往下掉了这么久，按刚动过的石头等
    ref_tau: float = 0.5             # 秒："平时的总压力"的平滑时间常数（跟着 Velostat 的蠕变慢慢变）


@dataclass(frozen=True)
class Stone:
    """垫面上的一颗石头（DATA_MODEL「垫面状态」）。"""
    id: int
    zone: int                 # 主区：压力最大的区，代表这颗石头在哪
    zones: frozenset[int]     # 压到的区
    x: float                  # 按压力加权的位置（控制台绘图单位）
    y: float
    strength: float           # 总压力，以放下阈值为单位（已做串扰补偿）
    placed_at: float
    moved_at: float           # 最近一次挪动（换主区）的时刻；没挪过等于 placed_at

    @property
    def radius(self) -> float:
        return math.hypot(self.x, self.y)

    @property
    def angle(self) -> float:
        """角度（度），0° 在 12 点方向，顺时针。"""
        return math.degrees(math.atan2(self.x, self.y)) % 360.0


@dataclass
class _Track:
    id: int
    zones: set[int]
    anchor: int
    placed_at: float
    moved_at: float
    shifted_at: float = -math.inf            # 最近一次真正挪动（换主区）的时刻；刚放下不算
    grew_at: float = -math.inf               # 最近一次有区的压力新升到够一颗石头的时刻
    strong: dict[int, float] = field(default_factory=dict)   # 区 → 压力升到够一颗石头的时刻
    split_ref: float | None = None           # 有区新升起来时，这颗石头平时的总压力
    split_since: float | None = None
    anchor_pending: tuple[int, float] | None = None   # 要换过去的主区和开始的时刻
    missing_since: float | None = None
    ref: float | None = None                 # 平时的总压力
    fading_since: float | None = None
    last_t: float | None = None
    x: float = 0.0
    y: float = 0.0
    strength: float = 0.0

    def snapshot(self) -> Stone:
        return Stone(self.id, self.anchor, frozenset(self.zones), self.x, self.y, self.strength,
                     self.placed_at, self.moved_at)

    def locate(self, zones: set[int], uc: np.ndarray) -> None:
        idx = np.fromiter(zones, dtype=np.int64, count=len(zones))
        w = uc[idx]
        self.x = float((w * _X[idx]).sum() / w.sum())
        self.y = float((w * _Y[idx]).sum() / w.sum())
        self.strength = float(w.sum())


@dataclass
class _Candidate:
    zones: set[int]
    born: float
    strong_since: float | None = None


def _component(seed: int, allowed: set[int]) -> set[int]:
    """从 seed 出发、只经过 allowed 里相邻的区，连成的一块。"""
    out, todo = {seed}, deque([seed])
    while todo:
        for n in NEIGHBOURS[todo.popleft()]:
            if n in allowed and n not in out:
                out.add(n)
                todo.append(n)
    return out


class StoneTracker:
    def __init__(self, params: TrackerParams):
        self.p = params
        self.threshold = np.asarray(params.place_threshold, dtype=np.float64)
        self.strips = np.asarray(params.strips, dtype=np.int64)
        self._tracks: list[_Track] = []
        self._candidates: list[_Candidate] = []
        self._ids = 0

    def reset(self) -> None:
        self._tracks.clear()
        self._candidates.clear()

    @property
    def stones(self) -> tuple[Stone, ...]:
        return tuple(tr.snapshot() for tr in self._tracks)

    def update(self, t: float, values: np.ndarray) -> list[MatEvent]:
        p = self.p
        v = np.asarray(values, dtype=np.float64)
        u = v / self.threshold
        strip_sum = np.bincount(self.strips, weights=v, minlength=32)
        uc = u * (1.0 + p.crosstalk * (strip_sum[self.strips] - v))
        pressed = uc >= p.floor

        # 已有的石头认领：先认自己的区，再认紧挨着的（同一个区够得着几颗时给最近的那颗）
        owner = np.full(NUM_ZONES, -1, dtype=np.int64)
        for tr in self._tracks:
            for z in tr.zones:
                if pressed[z] and owner[z] < 0:
                    owner[z] = tr.id
        by_id = {tr.id: tr for tr in self._tracks}
        reach: dict[int, list[int]] = {}
        for tr in self._tracks:
            if tr.missing_since is None:
                for z in {k for j in tr.zones for k in NEIGHBOURS[j]} - tr.zones:
                    if owner[z] < 0 and pressed[z]:
                        reach.setdefault(z, []).append(tr.id)
        for z, ids in reach.items():
            owner[z] = min(ids, key=lambda i: (_X[z] - by_id[i].x) ** 2 + (_Y[z] - by_id[i].y) ** 2)
        # 暂时找不到的石头：在隔一个区的范围里找回一块连着的压力，它消失之前就有的候选不算
        older = {}
        for c in self._candidates:
            for z in c.zones:
                older[z] = min(older.get(z, math.inf), c.born)
        for tr in self._tracks:
            if tr.missing_since is None or (owner == tr.id).any():
                continue
            area = {k for j in tr.zones for k in NEIGHBOURS2[j]} | tr.zones
            if ZONES[tr.anchor].ring == 0:
                area |= _INNERMOST
            free = {z for z in area if owner[z] < 0 and pressed[z] and older.get(z, math.inf) >= tr.missing_since}
            if free:
                blob = _component(max(free, key=lambda z: (uc[z], -z)), free)
                if tr.ref is None or sum(uc[z] for z in blob) >= p.reacquire * tr.ref:
                    for z in blob:
                        owner[z] = tr.id

        events: list[MatEvent] = []
        for tr in list(self._tracks):
            footprint = {int(z) for z in np.flatnonzero(owner == tr.id)}
            events += self._update_track(tr, footprint, uc, t)
        events += self._update_candidates(u, owner, uc, t)
        return events

    # ── 已有的石头 ──────────────────────────────────────────────────────

    def _moving(self, tr: _Track, t: float) -> bool:
        return t - tr.shifted_at <= self.p.moving_window or t - tr.grew_at <= self.p.moving_window

    def _update_track(self, tr: _Track, footprint: set[int], uc: np.ndarray, t: float) -> list[MatEvent]:
        p = self.p
        events: list[MatEvent] = []
        strength = float(sum(uc[z] for z in footprint))
        dt = 0.0 if tr.last_t is None else max(0.0, t - tr.last_t)
        tr.last_t = t

        if not footprint or strength < p.floor:
            if tr.missing_since is None:
                tr.missing_since = t
            sliding_off = tr.fading_since is not None and tr.missing_since - tr.fading_since >= p.fade_min - 1e-9
            if sliding_off or self._moving(tr, t):
                hold = p.center_hold if ZONES[tr.anchor].ring == 0 else p.release_hold_moving
            else:
                hold = p.release_hold
            if t - tr.missing_since >= hold - 1e-9:
                self._tracks.remove(tr)
                events.append(MatEvent(kind="lift", zone=tr.anchor, t=t, stone=tr.id))
            return events
        tr.missing_since = None

        # 哪些区的压力新升到够一颗石头
        for z in footprint:
            if uc[z] >= STRONG:
                if z not in tr.strong:
                    tr.strong[z] = t
                    tr.grew_at = t
            elif uc[z] < STRONG_OFF:
                tr.strong.pop(z, None)
        for z in [z for z in tr.strong if z not in footprint]:
            del tr.strong[z]
        new = {z for z, since in tr.strong.items() if t - since < p.split_window}
        core = footprint - new
        if not new:
            tr.split_ref = None
        elif tr.split_ref is None:
            # 记下这颗石头平时的总压力（滑动开始时原来的区已经在往下掉，不能拿上一帧比）
            tr.split_ref = tr.ref if tr.ref is not None else strength

        # 旁边又放了一颗：新升起来的区压力够一颗石头，原来的压力没有让出来，总压力多出了一颗石头
        split_pending = False
        if new and core and tr.split_ref is not None and tr.split_ref >= p.floor:
            gain = sum(uc[z] for z in new)
            kept = sum(uc[z] for z in core)
            if (gain >= p.split_gain and kept >= p.split_core * tr.split_ref
                    and gain + kept >= tr.split_ref + p.split_gain):
                if tr.split_since is None:
                    tr.split_since = t
                split_pending = True
                if t - tr.split_since >= p.split_hold - 1e-9:
                    events.append(self._spawn(new, uc, tr.split_since, t))
                    footprint = core
                    for z in new:
                        del tr.strong[z]
                    tr.split_since = tr.split_ref = None
                    split_pending = False
                    strength = float(sum(uc[z] for z in footprint))
            else:
                tr.split_since = None
        else:
            tr.split_since = None

        # 平时的总压力；在往下掉的时候不跟（判断"是不是滑走了"要和掉之前比）
        if tr.ref is None:
            tr.ref = strength
        if strength < p.fade_ratio * tr.ref:
            if tr.fading_since is None:
                tr.fading_since = t
        else:
            tr.fading_since = None
            if not split_pending:
                tr.ref += (1.0 - math.exp(-dt / p.ref_tau)) * (strength - tr.ref)

        # 主区：分出新石头的条件还在等的时候，只在原来的区里找，不往新石头那边挪
        options = core if split_pending and core else footprint
        best = max(options, key=lambda z: (uc[z], -z))
        switch = False
        if best != tr.anchor:
            if tr.anchor not in footprint:
                switch = True
            elif uc[best] >= p.anchor_switch * uc[tr.anchor]:
                if tr.anchor_pending is None or tr.anchor_pending[0] != best:
                    tr.anchor_pending = (best, t)
                switch = t - tr.anchor_pending[1] >= p.anchor_hold - 1e-9
            else:
                tr.anchor_pending = None
        else:
            tr.anchor_pending = None
        if switch:
            events.append(MatEvent(kind="move", zone=best, t=t, stone=tr.id, from_zone=tr.anchor))
            tr.anchor = best
            tr.moved_at = tr.shifted_at = t
            tr.anchor_pending = None

        tr.zones = footprint
        tr.locate(footprint, uc)
        return events

    def _spawn(self, zones: set[int], uc: np.ndarray, since: float, t: float) -> MatEvent:
        self._ids += 1
        anchor = max(zones, key=lambda z: (uc[z], -z))
        tr = _Track(self._ids, set(zones), anchor, placed_at=t, moved_at=t,
                    strong={z: since for z in zones if uc[z] >= STRONG})
        tr.locate(zones, uc)
        self._tracks.append(tr)
        return MatEvent(kind="place", zone=anchor, t=t, stone=tr.id)

    # ── 新出现的压力 ────────────────────────────────────────────────────

    def _update_candidates(self, u: np.ndarray, owner: np.ndarray, uc: np.ndarray, t: float) -> list[MatEvent]:
        p = self.p
        free = {int(z) for z in np.flatnonzero((owner < 0) & (u >= p.floor))}
        blobs: list[set[int]] = []
        while free:
            blob = _component(next(iter(free)), free)
            free -= blob
            blobs.append(blob)

        events: list[MatEvent] = []
        previous = self._candidates
        self._candidates = []
        for blob in blobs:
            match = max(previous, key=lambda c: len(c.zones & blob), default=None)
            if match is not None and match.zones & blob:
                previous.remove(match)
                cand = match
            else:
                cand = _Candidate(set(), born=t)
            cand.zones = blob
            if float(u[list(blob)].sum()) >= p.place_strength:
                if cand.strong_since is None:
                    cand.strong_since = t
                if t - cand.strong_since >= p.occupy_hold - 1e-9:
                    events.append(self._spawn(blob, uc, cand.strong_since, t))
                    continue
            else:
                cand.strong_since = None
            self._candidates.append(cand)
        return events
