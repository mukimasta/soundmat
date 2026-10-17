"""声音化：唯一做艺术决定的地方（system_design/SONIFICATION.md）。

``Sonification`` 在时钟的每一拍读取最新的垫面快照，取走上一拍之后积累的全部事件，
调用当前模式实例，把声音意图交给声音引擎、灯光意图交给灯光引擎、模式状态交给状态中心。
切换编排时新旧两个实例同时运行，声音引擎在两组输出之间交叉淡化，淡化结束后停止旧实例。
"""
from __future__ import annotations

import itertools
import logging
import queue
from dataclasses import dataclass
from typing import Callable

from ..clock import Beat
from ..exchange import Latest
from ..monitor.log import EventLog
from ..perception import Perception
from ..sound.engine import SoundEngine
from ..store import Store
from .intent import BeatOutput, LightIntent, SoundIntent
from .meters import Meter, resolve_meters
from .mode import Arrangement, LoadError, LoadPlan, Mode, ModeContext

log = logging.getLogger("soundmat.sonification")

ModeFactory = Callable[[Arrangement, ModeContext], Mode]
STATUS_PERIOD = 0.25  # 秒：引擎状态与切换进度写入状态中心的间隔


@dataclass
class ModeInstance:
    id: str
    arrangement: Arrangement
    mode: Mode
    plan: LoadPlan
    meters: tuple[Meter, ...] = ()
    last: BeatOutput | None = None
    retiring: bool = False
    failing: bool = False


class Sonification:
    def __init__(self, engine: SoundEngine, perception: Perception, store: Store,
                 events: EventLog, light: Latest[LightIntent], modes: dict[str, ModeFactory],
                 ctx: ModeContext, crossfade: float):
        self.engine = engine
        self.perception = perception
        self.store = store
        self.log = events
        self.light = light
        self.modes = modes
        self.ctx = ctx
        self.crossfade = crossfade
        self.instances: list[ModeInstance] = []
        self._events = perception.events.subscribe()
        self._pending: queue.Queue = queue.Queue()
        self._ids = itertools.count(1)
        self._next_status = 0.0
        self._switch_started: float | None = None
        # 激活新实例之前调用，例如素材库加载素材；抛出 LoadError 表示失败
        self.before_activate: list[Callable[[ModeInstance, float], None]] = []
        # 实例释放之后调用，例如素材库释放只被它使用的素材
        self.after_retire: list[Callable[[ModeInstance, float], None]] = []
        # 每拍结束时调用，例如把其他模块的状态按节奏写入状态中心
        self.after_beat: list[Callable[[float], None]] = []

    @property
    def active(self) -> ModeInstance | None:
        live = [i for i in self.instances if not i.retiring]
        return live[-1] if live else None

    def prepare(self, arrangement: Arrangement) -> ModeInstance:
        """加载编排，建立模式实例（还未激活）。可在任何线程调用；失败抛出 ``LoadError``。"""
        factory = self.modes.get(arrangement.mode)
        if factory is None:
            raise LoadError(f"没有名为 {arrangement.mode} 的模式")
        mode = factory(arrangement, self.ctx)
        plan = mode.load()
        mode.plan = plan
        meters = resolve_meters(arrangement, plan)
        iid = f"{arrangement.id}-{next(self._ids)}"
        return ModeInstance(iid, arrangement, mode, plan, meters)

    def switch(self, inst: ModeInstance) -> None:
        """请求在下一拍激活这个实例；当前实例交叉淡化后停止。"""
        self._pending.put(inst)

    def run_in_beat(self, fn: Callable[[float], None]) -> None:
        """在下一拍开始时、节拍线程里执行 ``fn(now)``。声音引擎只能在节拍线程里调用。"""
        self._pending.put(fn)

    # ── 节拍 ────────────────────────────────────────────────────────────

    def on_beat(self, beat: Beat) -> None:
        now = beat.t
        while not self._pending.empty():
            item = self._pending.get_nowait()
            if isinstance(item, ModeInstance):
                self._activate(item, now)
            else:
                try:
                    item(now)
                except Exception:
                    log.exception("节拍线程中的命令出错")
        self.engine.backend.flush()

        events = self._events.drain()
        snap = self.perception.snapshot.get()
        active = self.active
        for inst in list(self.instances):
            out = self._tick(inst, beat, snap, events)
            self.engine.apply(inst.id, out.sound, now)
            if inst is active:
                self.light.set(out.light)
                self.store.set("status.current.modeStatus", out.status.to_json())

        for iid in self.engine.tick(now):
            self._finish(iid, now)

        if now >= self._next_status:
            self._next_status = now + STATUS_PERIOD
            self._publish_status(now)
        for fn in self.after_beat:
            fn(now)
        self.engine.backend.flush()

    def _tick(self, inst: ModeInstance, beat: Beat, snap, events) -> BeatOutput:
        try:
            out = inst.mode.tick(beat, snap, events)
            if inst.failing:
                inst.failing = False
                self.log.info(f"{inst.arrangement.title}：模式恢复正常")
            inst.last = out
            return out
        except Exception as e:
            log.exception("模式出错")
            if not inst.failing:
                inst.failing = True
                self.log.error(f"{inst.arrangement.title}：模式出错（{e}），保持上一拍的声音")
            prev = inst.last or BeatOutput()
            # 保持上一拍的持续声部和全局参数；定时事件已经发出过，不再重复
            return BeatOutput(SoundIntent(prev.sound.voices, (), prev.sound.globals), prev.light, prev.status)

    def _activate(self, inst: ModeInstance, now: float) -> None:
        try:
            for fn in self.before_activate:
                fn(inst, now)
        except LoadError as e:
            self.log.error(f"无法切换到 {inst.arrangement.title}：{e}")
            return
        previous = [i for i in self.instances if not i.retiring]
        fade = self.crossfade if previous else 0.0
        self.engine.add_instance(inst.id, inst.plan.buses, now, fade, inst.plan.fx)
        for old in previous:
            old.retiring = True
            self.engine.retire_instance(old.id, now, fade)
        inst.mode.start(now)
        self.instances.append(inst)
        self.perception.set_control_zones(inst.plan.control_zones)
        self._switch_started = now if previous else None
        a = inst.arrangement
        self.store.update({
            "status.current.arrangement": a.id,
            "status.current.mode": a.mode,
            "status.current.meters": [m.to_json() for m in inst.meters],
        })
        self.log.info(f"开始演奏：{a.title}")

    def _finish(self, iid: str, now: float) -> None:
        for inst in [i for i in self.instances if i.id == iid]:
            self.instances.remove(inst)
            inst.mode.stop()
            for fn in self.after_retire:
                fn(inst, now)

    def _publish_status(self, now: float) -> None:
        switching = None
        active = self.active
        if self._switch_started is not None and active is not None:
            p = (now - self._switch_started) / self.crossfade if self.crossfade > 0 else 1.0
            if p >= 1.0 or not any(i.retiring for i in self.instances):
                self._switch_started = None
            else:
                old = next((i for i in self.instances if i.retiring), None)
                switching = {"from": old.arrangement.id if old else None,
                             "to": active.arrangement.id, "progress": round(p, 3)}
        self.store.update({
            "status.current.switching": switching,
            "status.audio.engine": self.engine.status(),
        })
