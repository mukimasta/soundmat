"""JamLedRenderer：合成 108 路 LED（移植自 web demo computeLedStates）。

状态机（JAM_DESIGN §7）：
- 播完（form_ended & !playing）：仅四象限卡位呼吸，其余灭。
- 空闲（!playing & !form_ended）：全环白呼吸 0–50%，卡位红呼吸 50–100%。
- 播放中：无环境白场；白色扫描尾迹 + 石头淡标记 + 卡位呼吸；命中闪、预览短效叠加。

合成顺序：模式基底 → 叠预览 → 叠命中（与基底取更亮）。
"""
from __future__ import annotations

from .layers import (
    CARDINAL_BREATH_MIN,
    CARDINAL_LED_INDICES,
    LED_COUNT,
    PREVIEW_DURATION,
    RED_FULL,
    RED_MUTED,
    SCAN_HIT_DURATION,
    SCAN_HIT_FALLOFF,
    SCAN_HIT_OFFSETS,
    SWEEP_OPACITY_BY_DIST,
    SWEEP_TRAIL_WIDTH,
    WHITE,
    blend_over,
    breath_phase,
    flatten,
    led_distance_behind,
    led_index_for_angle,
    led_index_for_sector,
    led_indices_for_sector_span,
    led_signed_offset,
    max_state,
    pulse_mix,
    rgba,
    ring_led_rgb,
    scan_hit_mix,
    wrap_led_distance,
)


class JamLedRenderer:
    def __init__(self, ring_configs=None):
        self.ring_configs = ring_configs or {}
        self._previews: list[dict] = []   # {sector, ring, start}
        self._flashes: list[dict] = []

    # ── 短效注入 ──
    def on_scan_hit(self, sector: int | None, ring: int, now: float) -> None:
        if sector is None:
            return
        self._flashes.append({"sector": sector, "ring": ring, "start": now})

    def on_preview(self, sector: int, ring: int, now: float) -> None:
        self._previews.append({"sector": sector, "ring": ring, "start": now})

    def _prune(self, now: float) -> None:
        self._flashes = [f for f in self._flashes if now - f["start"] < SCAN_HIT_DURATION + 0.05]
        self._previews = [p for p in self._previews if now - p["start"] < PREVIEW_DURATION + 0.1]

    # ── 各模式基底 ──
    def _idle_transport_led(self, i: int, t: float):
        breath = breath_phase(t)
        is_cardinal = i in CARDINAL_LED_INDICES
        opacity = (CARDINAL_BREATH_MIN + (1 - CARDINAL_BREATH_MIN) * breath
                   if is_cardinal else 0.5 * breath)
        if i == 0:
            return rgba(RED_FULL, opacity)
        if is_cardinal:
            return rgba(RED_MUTED, opacity)
        return rgba(WHITE, opacity)

    def _form_ended_led(self, i: int, t: float):
        if i in CARDINAL_LED_INDICES:
            return self._idle_transport_led(i, t)
        return rgba(WHITE, 0.0)

    def _playing_led(self, i: int, t: float, sweep_angle: float, markers):
        state = rgba(WHITE, 0.0)
        sweep_led = led_index_for_angle(sweep_angle)
        behind = led_distance_behind(i, sweep_led)
        if behind is not None and behind <= SWEEP_TRAIL_WIDTH:
            op = SWEEP_OPACITY_BY_DIST[behind] if behind < len(SWEEP_OPACITY_BY_DIST) else 0.0
            if op > 0:
                state = rgba(WHITE, op)
        for ring, slc in markers:
            if wrap_led_distance(i, led_index_for_sector(slc)) <= 1:
                state = blend_over(state, rgba(ring_led_rgb(ring), 0.22), 0.55)
        if i in CARDINAL_LED_INDICES:
            state = self._idle_transport_led(i, t)
        return state

    # ── 短效查询 ──
    def _preview_for_led(self, i: int, t: float):
        best_mix, ring = 0.0, None
        for p in self._previews:
            if i not in led_indices_for_sector_span(p["sector"], 2):
                continue
            mix = pulse_mix(t - p["start"])
            if mix > best_mix:
                best_mix, ring = mix, p["ring"]
        return best_mix, ring

    def _scan_hit_for_led(self, i: int, t: float):
        strength, ring = 0.0, None
        for f in self._flashes:
            center = led_index_for_sector(f["sector"])
            offset = led_signed_offset(i, center)
            if offset not in SCAN_HIT_OFFSETS:
                continue
            env = scan_hit_mix(t - f["start"])
            falloff = SCAN_HIT_FALLOFF[abs(offset)] if abs(offset) < len(SCAN_HIT_FALLOFF) else 0.2
            mix = env * falloff
            if mix > strength:
                strength, ring = mix, f["ring"]
        return strength, ring

    # ── 合成 ──
    def render(self, now: float, *, sweep_angle: float, playing: bool,
               form_ended: bool = False, control_count: int = 0,
               stones=None) -> list[tuple[int, int, int]]:
        self._prune(now)
        stones = stones or []
        post_play = form_ended and not playing
        idle = not post_play and not playing
        markers = stones if playing else []

        out: list[tuple[int, int, int]] = []
        for i in range(LED_COUNT):
            if post_play:
                base = self._form_ended_led(i, now)
            elif idle:
                base = self._idle_transport_led(i, now)
            else:
                base = self._playing_led(i, now, sweep_angle, markers)

            if not post_play:
                mix, ring = self._preview_for_led(i, now)
                if mix > 0:
                    rgb = ring_led_rgb(ring) if ring is not None else RED_MUTED
                    base = blend_over(base, rgba(rgb, 1.0), mix)

            if playing:
                strength, ring = self._scan_hit_for_led(i, now)
                if strength > 0.02:
                    rgb = ring_led_rgb(ring) if ring is not None else RED_FULL
                    base = max_state(base, rgba(rgb, strength))

            out.append(flatten(base))
        return out
