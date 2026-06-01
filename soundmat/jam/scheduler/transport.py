"""Transport：启停 + 主时钟 + 曲终判定（设计文档 §6.2 / §9）。

全局 `musical_time` 从 0 起计，达到曲式总时长后曲终（form_ended），扫描停止；须清空
R0/R1 石头后才能 reset 重新开拍。开拍/停止由 R0/R1 控制石数驱动（见 sensor_state），
这里只维护时钟与状态机。
"""
from __future__ import annotations

from ..theory.tempo import BEATS_PER_BAR


class Transport:
    def __init__(self, bpm: float, form_total_bars: int):
        self.bpm = float(bpm)
        self.form_total_bars = form_total_bars
        self.musical_time = 0.0
        self.playing = False
        self.form_ended = False

    @property
    def form_duration(self) -> float:
        return self.form_total_bars * BEATS_PER_BAR * (60.0 / self.bpm)

    def set_bpm(self, bpm: float) -> None:
        self.bpm = float(bpm)

    # ── 状态机 ──
    def start(self) -> bool:
        """请求开拍；返回是否为本次新开拍（首拍触发用）。曲终态下不开拍。"""
        if self.form_ended or self.playing:
            return False
        self.playing = True
        return self.musical_time == 0.0

    def pause(self) -> None:
        self.playing = False

    def reset(self) -> None:
        self.musical_time = 0.0
        self.playing = False
        self.form_ended = False

    # ── 推进 ──
    def advance(self, dt: float) -> tuple[float, float, bool]:
        """前进 dt 秒。返回 (prev_time, curr_time, just_ended)。

        curr_time 被钳到 form_duration；到达即 form_ended（playing 置 False），
        但本帧 prev→curr 区间仍返回给伴奏 tick，保证最后一拍发声。
        """
        if not self.playing or self.form_ended:
            return self.musical_time, self.musical_time, False
        prev = self.musical_time
        nxt = prev + dt
        dur = self.form_duration
        if nxt >= dur:
            self.musical_time = dur
            self.form_ended = True
            self.playing = False
            return prev, dur, True
        self.musical_time = nxt
        return prev, nxt, False
