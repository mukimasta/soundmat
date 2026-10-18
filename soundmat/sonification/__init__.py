"""声音化：唯一做艺术决定的地方（system_design/SONIFICATION.md）。

``Sonification`` 在时钟的每一拍读取最新的垫面快照，取走上一拍之后积累的全部事件，
调用当前模式实例，把声音意图交给声音引擎、灯光意图交给灯光引擎、模式状态交给状态中心。
切换编排时新编排立即开始，旧编排在很短的时间里淡出（只为避免咔嗒声）后停止，不交叉淡化。

节拍线程只做演奏本身：模式、声音引擎、灯光意图，以及自己的状态（状态中心的 ``status.current``、
``status.engine``、``status.assets``）。电平由别的线程按需采样（``sample_levels``），
其他模块的状态由它们自己或系统监测发布。
"""
from __future__ import annotations

import itertools
import logging
import queue
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from ..clock import Beat
from ..exchange import Latest
from ..intent import BeatOutput, LightIntent, ModeStatus, SoundIntent
from ..monitor.log import EventLog
from ..perception import Perception
from ..sound.engine import SoundEngine
from ..store import Store
from .meters import Meter, resolve_meters
from .mode import Arrangement, LoadError, LoadPlan, Mode, ModeContext

if TYPE_CHECKING:   # 素材库引用了编排的 LoadError，运行时从这里导入会形成循环
    from ..sound.assets import AssetLibrary

log = logging.getLogger("soundmat.sonification")

ModeFactory = Callable[[Arrangement, ModeContext], Mode]
STATUS_PERIOD = 0.25  # 秒：引擎状态写入状态中心的间隔
STOP_FADE = 0.3       # 秒：切换编排时旧编排淡出的时长，只为避免咔嗒声


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
    def __init__(self, engine: SoundEngine, assets: AssetLibrary, perception: Perception, store: Store,
                 events: EventLog, light: Latest[LightIntent], modes: dict[str, ModeFactory],
                 ctx: ModeContext):
        self.engine = engine
        self.assets = assets
        self.perception = perception
        self.state = store.writer("status.current", "status.engine", "status.assets")
        self.log = events
        self.light = light
        self.modes = modes
        self.ctx = ctx
        self.instances: list[ModeInstance] = []
        # 正在演奏的实例。只在节拍线程里改，其他线程可以直接读这个引用
        self.active: ModeInstance | None = None
        self.levels: Latest[dict] = Latest()   # 总输出和每根电平条的电平，见 sample_levels
        self._events = perception.events.subscribe()
        self._pending: queue.Queue = queue.Queue()
        self._ids = itertools.count(1)
        self._next_status = 0.0
        self._last_status: ModeStatus | None = None
        # 每拍结束时调用 fn(now, 当前实例这一拍的输出)，例如录制把它写进会话数据
        self.after_beat: list[Callable[[float, BeatOutput | None], None]] = []
        self.state.set("status.current", {
            "virtual": perception.source == "virtual", "arrangement": None, "mode": None,
            "modeStatus": None, "meters": []})
        self.state.set("status.assets", {"missing": []})

    # ── 命令（任意线程）─────────────────────────────────────────────────

    def prepare(self, arrangement: Arrangement) -> ModeInstance:
        """加载编排，建立模式实例（还未激活）。失败抛出 ``LoadError``。"""
        factory = self.modes.get(arrangement.mode)
        if factory is None:
            raise LoadError(f"没有名为 {arrangement.mode} 的模式")
        mode = factory(arrangement, self.ctx)
        plan = mode.load()
        mode.plan = plan
        meters = resolve_meters(arrangement, plan)
        iid = f"{arrangement.id}-{next(self._ids)}"
        return ModeInstance(iid, arrangement, mode, plan, meters)

    def play(self, arrangement: Arrangement) -> None:
        """加载一份编排，在下一拍切换过去；加载失败时保持当前编排，抛出 ``LoadError``。"""
        try:
            inst = self.prepare(arrangement)
        except LoadError as e:
            self.log.error(f"无法加载 {arrangement.title}：{e}")
            raise
        self._pending.put(inst)

    def run_in_beat(self, fn: Callable[[float], None]) -> None:
        """在下一拍开始时、节拍线程里执行 ``fn(now)``。声音引擎只能在节拍线程里调用。"""
        self._pending.put(fn)

    def sample_levels(self, now: float) -> None:
        """读取当前实例的电平，更新 ``levels``。在节拍线程之外调用（例如每秒 10 次）。"""
        active = self.active
        meters = [m.buses for m in active.meters] if active else []
        lv = self.engine.backend.levels(active.id if active else None, meters, now)
        if lv is not None:
            self.levels.set(lv)

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
                if out.status != self._last_status:
                    self._last_status = out.status
                    self.state.set("status.current.modeStatus", out.status.to_json())

        for iid in self.engine.tick(now):
            self._finish(iid, now)

        if now >= self._next_status:
            self._next_status = now + STATUS_PERIOD
            self._publish_status(now)
        output = active.last if active else None
        for fn in self.after_beat:
            fn(now, output)
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
            missing = self.assets.acquire(inst.id, inst.plan.assets, now)
        except LoadError as e:
            self.log.error(f"无法切换到 {inst.arrangement.title}：{e}")
            return
        a = inst.arrangement
        self.state.set("status.assets", {"missing": missing, "needed": len(inst.plan.assets),
                                         "state": self.assets.status()})
        if missing:
            self.log.warning(f"{a.title}：缺少 {len(missing)} 个声音素材，用到它们的声音不会发声")
        for old in [i for i in self.instances if not i.retiring]:
            old.retiring = True
            self.engine.retire_instance(old.id, now, STOP_FADE)
        self.engine.add_instance(inst.id, inst.plan.buses, now, inst.plan.fx, gain=10 ** (a.level / 20))
        inst.mode.start(now)
        self.instances.append(inst)
        self.active = inst
        self._last_status = None
        self.perception.set_control_zones(inst.plan.control_zones)
        self.state.update({
            "status.current.arrangement": a.id,
            "status.current.mode": a.mode,
            "status.current.meters": [m.to_json() for m in inst.meters],
        })
        self.log.info(f"开始演奏：{a.title}")

    def _finish(self, iid: str, now: float) -> None:
        for inst in [i for i in self.instances if i.id == iid]:
            self.instances.remove(inst)
            inst.mode.stop()
            self.assets.release(inst.id, now)

    def _publish_status(self, now: float) -> None:
        self.state.set("status.engine", self.engine.status())
