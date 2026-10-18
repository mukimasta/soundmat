"""声音引擎：把声音意图变成合成器服务执行的指令（system_design/SOUND_ENGINE.md）。

它不做任何艺术决定，只负责对账、声部预算、定时、混音结构与空间化，对所有模式一视同仁。
引擎不是线程安全的：只在声音化的节拍线程里调用。

定时只有两种：

- **有确定时刻的**（定时事件的 ``time``、持续声部的 ``start``，例如鼓点、扫描命中、下一小节的和声）：
  统一推后 ``sound.schedule_ahead`` 秒交给合成器服务。合成器服务要在音频缓冲开始计算之前收到指令
  才能按采样精度准时执行，推后的这一段就是留给它的提前量；主机偶尔慢一点也不影响节奏。
- **其余的一律立即**（没有时刻的事件和声部，例如放下石头时的预听；参数、音量、淡出、混音结构）：
  合成器服务收到后在下一个缓冲执行，越快越好，没有"迟到"一说。

一个声部之后的修改、淡出和释放，跟着它自己开始时的方式走：按时刻开始的，后续指令也按时刻排
（推后同样的提前量，并且不早于它的开始）；立即开始的，后续指令也立即。不能混用：合成器服务按时间戳
排队执行带时刻的指令，"立即"的指令却一到就执行；两者的先后取决于它和主机的时钟是否对齐，而树莓派
没有电池时钟，开机联网校时会让时钟跳变几分钟（2026-10-18 在 Pi 3B 上，带时刻的"开始"被压住、
立即的"停止"先执行，留下一直响的和声铺底）。
"""
from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Mapping, Sequence

from ..config import SoundConfig
from ..errors import InvalidRequest
from ..intent import Event, Position, SoundIntent, Source, Voice
from .backend import Backend
from .spatial import SpeakerGains, SpeakerLayout, voice_gains

log = logging.getLogger("soundmat.sound")

DEDUP_HORIZON = 30.0  # 秒：记住已发出的定时事件标识多久


class Phase(Enum):
    SOUNDING = "sounding"      # 持续声部（含淡入中）
    FADING_OUT = "fading_out"
    ONESHOT = "oneshot"        # 定时事件产生的单次声音，自然结束


@dataclass
class VoiceRecord:
    node: int
    instance: str
    key: str | None            # 持续声部的标识；单次声音为 None
    source: Source
    bus: str
    params: dict[str, float]
    position: Position | None
    priority: int
    category: str | None
    started: float
    phase: Phase
    fade_out: float = 0.5
    scheduled: bool = False    # 按时刻开始的（后续指令也按时刻排，见模块说明）


@dataclass
class InstanceRecord:
    id: str
    buses: list[str]
    fx: str | None = None
    gain: float = 1.0
    globals: dict[str, float] = field(default_factory=dict)
    voices: dict[str, int] = field(default_factory=dict)      # 持续声部标识 → 节点
    finished: set[str] = field(default_factory=set)            # 自然结束、仍在意图里的声部
    rejected: set[str] = field(default_factory=set)            # 因预算未能发声的声部
    retire_at: float | None = None


@dataclass
class EngineStats:
    yields: int = 0            # 为新声部让位的次数
    rejected: int = 0          # 因预算放弃发声的次数
    late: int = 0              # 迟到而丢弃的定时事件
    duplicates: int = 0        # 按标识去重丢掉的定时事件
    restarts: int = 0          # 检测到合成器服务重启的次数

    def to_json(self) -> dict:
        return dict(self.__dict__)


class SoundEngine:
    def __init__(self, backend: Backend, cfg: SoundConfig, layout: SpeakerLayout,
                 orientation: float = 0.0):
        self.backend = backend
        self.cfg = cfg
        self.layout = layout
        self.orientation = orientation
        self.voices: dict[int, VoiceRecord] = {}
        self.instances: dict[str, InstanceRecord] = {}
        self.stats = EngineStats()
        self._nodes = itertools.count(1000)
        self._seen_events: dict[str, float] = {}
        self._master: dict[str, float] = {}
        # 合成器服务重启或混音结构重建后调用，例如素材库重新加载素材
        self.on_rebuild: list[Callable[[float], None]] = []

    # ── 混音结构与模式实例 ──────────────────────────────────────────────

    def add_instance(self, instance: str, buses: Sequence[str], now: float, fade: float = 0.0,
                     fx: str | None = None, gain: float = 1.0) -> None:
        """为一个模式实例建立混音结构，按 ``fade`` 秒淡入到 ``gain``（切换编排时的交叉淡化）。

        ``fx`` 是共用效果的音色；``gain`` 是这份编排的整体电平（线性），让各编排的响度一致。
        """
        rec = InstanceRecord(instance, list(buses), fx=fx, gain=gain)
        self.instances[instance] = rec
        self.backend.create_mix(instance, rec.buses, self.layout.channels, now, fx)
        self.backend.set_mix_gain(instance, gain, fade, now)

    def retire_instance(self, instance: str, now: float, fade: float) -> None:
        """让一个模式实例的输出在 ``fade`` 秒内淡出，之后整体释放。"""
        rec = self.instances.get(instance)
        if rec is None or rec.retire_at is not None:
            return
        rec.gain = 0.0
        rec.retire_at = now + fade
        self.backend.set_mix_gain(instance, 0.0, fade, now)

    # ── 对账 ────────────────────────────────────────────────────────────

    def apply(self, instance: str, intent: SoundIntent, now: float) -> None:
        inst = self.instances.get(instance)
        if inst is None:
            raise KeyError(f"未知的模式实例：{instance}")
        desired: dict[str, Voice] = {}
        for v in intent.voices:
            desired[v.id] = v

        for key in list(inst.voices):
            if key not in desired:
                self._release(inst.voices.pop(key), now)
        inst.finished &= desired.keys()
        inst.rejected &= desired.keys()

        for key, v in desired.items():
            node = inst.voices.get(key)
            if node is not None:
                rec = self.voices[node]
                if rec.source != v.source or rec.bus != v.bus:
                    # 声源变了：旧声部淡出，新声部淡入，两者交叉
                    self._release(inst.voices.pop(key), now)
                    node = None
                else:
                    self._update(rec, v, now)
                    continue
            if key in inst.finished:
                continue
            self._start_voice(inst, v, now)

        changed = {k: val for k, val in intent.globals.items() if inst.globals.get(k) != val}
        if changed:
            inst.globals.update(changed)
            self.backend.set_globals(instance, changed, now)

        for e in intent.events:
            self._event(inst, e, now)

    def _update(self, rec: VoiceRecord, v: Voice, now: float) -> None:
        changed = {k: val for k, val in v.params.items() if rec.params.get(k) != val}
        gains = None
        if v.position != rec.position:
            rec.position = v.position
            gains = self._gains(v.position)
        if changed or gains is not None:
            rec.params.update(changed)
            self.backend.set_voice(rec.node, changed, gains, self._after_start(rec, now))
        rec.priority = v.priority
        rec.category = v.category
        rec.fade_out = v.fade_out

    def _start_voice(self, inst: InstanceRecord, v: Voice, now: float) -> None:
        if not self._make_room(v.priority, v.category, now):
            if v.id not in inst.rejected:
                inst.rejected.add(v.id)
                self.stats.rejected += 1
            return
        inst.rejected.discard(v.id)
        # 有开始时刻的（例如 Jam 下一小节的和声）按时刻排；已经过去或没有时刻的立即开始
        at = now if v.start is None else max(now, self._scheduled(v.start))
        node = next(self._nodes)
        self.voices[node] = VoiceRecord(
            node=node, instance=inst.id, key=v.id, source=v.source, bus=v.bus,
            params=dict(v.params), position=v.position, priority=v.priority,
            category=v.category, started=at, phase=Phase.SOUNDING, fade_out=v.fade_out,
            scheduled=v.start is not None,
        )
        inst.voices[v.id] = node
        self.backend.start_voice(node, inst.id, v.source, v.bus, v.params,
                                 self._gains(v.position), v.fade_in, at, oneshot=False)

    def _release(self, node: int, now: float) -> None:
        rec = self.voices.get(node)
        if rec is None or rec.phase is Phase.FADING_OUT:
            return
        rec.phase = Phase.FADING_OUT
        self.backend.release_voice(node, rec.fade_out, self._after_start(rec, now))

    # ── 定时事件 ────────────────────────────────────────────────────────

    def _event(self, inst: InstanceRecord, e: Event, now: float) -> None:
        if e.id in self._seen_events:
            self.stats.duplicates += 1
            return
        self._seen_events[e.id] = now if e.time is None else e.time
        if e.time is None:
            at = now                                   # 立即
        else:
            at = self._scheduled(e.time)
            if now - at > self.cfg.late_tolerance:     # 主机卡得太久，这个音已经错过了：丢弃
                self.stats.late += 1
                return
            at = max(at, now)
        if not self._make_room(e.priority, e.category, now):
            self.stats.rejected += 1
            return
        node = next(self._nodes)
        self.voices[node] = VoiceRecord(
            node=node, instance=inst.id, key=None, source=e.source, bus=e.bus,
            params=dict(e.params), position=e.position, priority=e.priority,
            category=e.category, started=at, phase=Phase.ONESHOT, scheduled=e.time is not None,
        )
        self.backend.start_voice(node, inst.id, e.source, e.bus, e.params,
                                 self._gains(e.position), 0.0, at, oneshot=True)

    # ── 声部预算 ────────────────────────────────────────────────────────

    def category_count(self, category: str) -> int:
        return sum(1 for r in self.voices.values() if r.category == category)

    def _make_room(self, priority: int, category: str | None, now: float) -> bool:
        limit = self.cfg.voice_budget_categories.get(category) if category else None
        while True:
            if len(self.voices) >= self.cfg.voice_budget_total:
                scope = list(self.voices.values())
            elif limit is not None and self.category_count(category) >= limit:
                scope = [r for r in self.voices.values() if r.category == category]
            else:
                return True
            victim = self._pick_victim(scope, priority, now)
            if victim is None:
                return False
            self._evict(victim, now)
            self.stats.yields += 1

    @staticmethod
    def _pick_victim(scope: list[VoiceRecord], priority: int, now: float) -> VoiceRecord | None:
        fading = [r for r in scope if r.phase is Phase.FADING_OUT]
        if fading:
            return min(fading, key=lambda r: r.started)
        # 只让已经开始发声的声部让位：还没到时刻的单次声音在合成器服务里还不存在
        lower = [r for r in scope if r.priority < priority and r.started <= now]
        if lower:
            return min(lower, key=lambda r: r.started)
        return None

    def _evict(self, rec: VoiceRecord, now: float) -> None:
        self.voices.pop(rec.node, None)
        self.backend.free_voice(rec.node, self._after_start(rec, now))
        if rec.key is not None:
            inst = self.instances.get(rec.instance)
            if inst and inst.voices.get(rec.key) == rec.node:
                del inst.voices[rec.key]

    # ── 例行维护 ────────────────────────────────────────────────────────

    def tick(self, now: float) -> list[str]:
        """处理合成器服务的通知，释放淡出完毕的模式实例。返回已释放的实例标识。"""
        ev = self.backend.poll(now)
        if ev.restarted:
            log.warning("合成器服务重新启动过，重建混音结构并重新对账")
            self.stats.restarts += 1
            self.rebuild(now, free_old=False)
        for node in ev.ended:
            rec = self.voices.pop(node, None)
            if rec is None or rec.key is None:
                continue
            inst = self.instances.get(rec.instance)
            if inst and inst.voices.get(rec.key) == node:
                # 有固定长度的持续声部自然结束：在它离开意图之前不再重新开始
                del inst.voices[rec.key]
                inst.finished.add(rec.key)

        retired = []
        for iid, inst in list(self.instances.items()):
            if inst.retire_at is not None and inst.retire_at <= now:
                own = [rec for rec in self.voices.values() if rec.instance == iid]
                # 每个声部的释放都按它自己的时间方式，排在它开始之后；混音结构等它们都释放了再释放
                at = max([now] + [self._after_start(rec, now) for rec in own])
                for rec in own:
                    self.voices.pop(rec.node)
                    self.backend.free_voice(rec.node, at)
                self.backend.free_mix(iid, at)
                del self.instances[iid]
                retired.append(iid)

        horizon = now - DEDUP_HORIZON
        if len(self._seen_events) > 512:
            self._seen_events = {k: t for k, t in self._seen_events.items() if t >= horizon}
        return retired

    def rebuild(self, now: float, free_old: bool = True) -> None:
        """重建全部混音结构；声部表清空，下一次对账时所有持续声部重新开始。

        合成器服务重启后（``free_old=False``，旧节点已不存在），或音箱数量改变时使用。
        """
        # 先释放旧的再重建，用同一个时刻保证顺序；要释放的声音里有排着还没开始的，就等到它们的时刻
        at = max([now] + [rec.started for rec in self.voices.values()]) if free_old else now
        if free_old:
            for node in list(self.voices):
                self.backend.free_voice(node, at)
            for iid in self.instances:
                self.backend.free_mix(iid, at)
        self.voices.clear()
        for fn in self.on_rebuild:
            fn(now)
        if self._master:
            self.backend.set_master(self._master, at)
        for inst in self.instances.values():
            self.backend.create_mix(inst.id, inst.buses, self.layout.channels, at, inst.fx)
            self.backend.set_mix_gain(inst.id, inst.gain, 0.0, at)
            if inst.globals:
                self.backend.set_globals(inst.id, inst.globals, at)
            inst.voices.clear()
            inst.finished.clear()
            inst.rejected.clear()

    # ── 总输出与音箱布局 ────────────────────────────────────────────────

    def set_master(self, params: Mapping[str, float], now: float) -> None:
        changed = {k: v for k, v in params.items() if self._master.get(k) != v}
        if changed:
            self._master.update(changed)
            self.backend.set_master(changed, now)

    def set_layout(self, layout: SpeakerLayout, orientation: float, now: float) -> None:
        """修改音箱布局或垫面朝向。声道数不变时只重新分配增益；变了则重建混音结构。"""
        channels_changed = layout.channels != self.layout.channels
        self.layout, self.orientation = layout, orientation
        if channels_changed:
            self.rebuild(now)
            return
        for rec in self.voices.values():
            if rec.phase is not Phase.ONESHOT:
                self.backend.set_voice(rec.node, {}, self._gains(rec.position), self._after_start(rec, now))

    # ── 辅助 ────────────────────────────────────────────────────────────

    def _scheduled(self, t: float) -> float:
        """有确定时刻的声音交给合成器服务的执行时刻：统一推后 ``schedule_ahead`` 秒（见模块说明）。"""
        return t + self.cfg.schedule_ahead

    def _after_start(self, rec: VoiceRecord, now: float) -> float:
        """对一个声部的后续指令的执行时刻：跟着它开始时的方式走（见模块说明），并且不早于它的开始。"""
        at = self._scheduled(now) if rec.scheduled else now
        return max(at, rec.started)

    def _gains(self, position: Position | None) -> SpeakerGains:
        return voice_gains(position, self.layout, self.orientation)

    def test_tone(self, channel: int, now: float) -> None:
        """在一个声道上放 1 秒测试音，确认每只音箱接对了位置。"""
        self.check_channel(channel)
        self.backend.test_tone(channel, now)

    def check_channel(self, channel: int) -> None:
        if not 0 <= channel < self.layout.channels:
            raise InvalidRequest(f"声道 {channel} 超出当前音箱布局（共 {self.layout.channels} 只）")

    def counters(self) -> dict[str, int]:
        """给系统监测：迟到丢弃、让位、因预算放弃的累计数。只读整数，可以在任意线程调用。"""
        st = self.stats
        return {"late": st.late, "yields": st.yields, "rejected": st.rejected}

    def status(self) -> dict:
        cats = {c: self.category_count(c) for c in self.cfg.voice_budget_categories}
        return {
            "voices": len(self.voices),
            "budget": self.cfg.voice_budget_total,
            "categories": cats,
            **self.stats.to_json(),
        }
