"""运行管理：唯一能启动和停止其他模块的地方（ARCHITECTURE「灯光引擎、设备连接与运行管理」）。

它按顺序建立各模块并把它们连起来，协调编排切换，决定失败时重试、降级还是退出。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ..clock import BeatClock, system_time
from ..config import ROOT, Config
from ..control import ControlContext
from ..device import DeviceLink, RawFrame
from ..light import LightEngine
from ..exchange import Latest
from ..monitor.log import EventLog
from ..perception import Perception
from ..perception.signal import Signal
from ..perception.virtual import VirtualMat
from ..sonification import ModeFactory, ModeInstance, Sonification
from ..sonification.ambient import AmbientMode
from ..sonification.jam import JamMode
from ..sonification.arrangements import ARRANGEMENTS_DIR, discover
from ..sonification.intent import LightIntent
from ..sonification.mode import Arrangement, LoadError, ModeContext
from ..sound.assets import AssetLibrary
from ..sound.backend import Backend, RecordingBackend
from ..sound.engine import SoundEngine
from ..sound.scsynth import ScsynthBackend
from ..sound.spatial import SpeakerLayout
from ..store import Store
from ..store.settings import Settings

log = logging.getLogger("soundmat")

MODES: dict[str, ModeFactory] = {"ambient": AmbientMode, "jam": JamMode}


@dataclass
class Options:
    virtual: bool = False
    backend: Backend | None = None        # 默认使用不发声的记录型引擎
    modes: dict[str, ModeFactory] = field(default_factory=lambda: dict(MODES))
    data_dir: Path = ROOT / "data"
    serial_port: str = "auto"
    synth: str = "recording"              # recording（不发声）或 scsynth
    device: DeviceLink | None = None      # 测试时注入模拟控制器
    arrangements_dir: Path = ARRANGEMENTS_DIR
    seed: int | None = None


class Supervisor:
    def __init__(self, config: Config, options: Options | None = None):
        self.config = cfg = config
        self.options = opts = options or Options()
        self.store = Store({
            "status": {
                "current": {"virtual": opts.virtual, "arrangement": None, "mode": None,
                            "modeStatus": None, "switching": None},
                "audio": {"assets": {"missing": []}},
                "log": [],
            },
            "catalog": {"arrangements": []},
        })
        self.events = EventLog(self.store)
        self.settings = Settings(self.store, opts.data_dir)

        source = "virtual" if opts.virtual else "controller"
        self.perception = Perception(cfg.mat, source=source)
        self.virtual: VirtualMat | None = VirtualMat(self.perception.feed) if opts.virtual else None

        if opts.backend is not None:
            self.backend: Backend = opts.backend
        elif opts.synth == "scsynth":
            self.backend = ScsynthBackend(cfg.synth.host, cfg.synth.port, cfg.synth.synthdefs_path)
        else:
            self.backend = RecordingBackend()
        self.engine = SoundEngine(self.backend, cfg.sound, self._layout(), self.settings.get("sound.orientation", 0.0))
        self.assets = AssetLibrary(Path(self.settings.get("run.soundLibrary")), cfg.sound.asset_memory_mb, self.backend)
        self.engine.on_rebuild.append(self.assets.reload_all)
        if isinstance(self.backend, ScsynthBackend):
            self.backend.resolve_asset = self.assets.info
        self.levels: Latest[dict] = Latest()
        self._next_levels = 0.0

        self.light: Latest[LightIntent] = Latest(LightIntent())
        self.sonification = Sonification(
            self.engine, self.perception, self.store, self.events, self.light,
            modes=opts.modes,
            ctx=ModeContext(led_count=cfg.light.led_count, setting=self.settings.get, seed=opts.seed),
            crossfade=cfg.sound.crossfade_seconds,
        )
        self.sonification.before_activate.append(self._acquire_assets)
        self.sonification.after_retire.append(lambda inst, now: self.assets.release(inst.id, now))
        self.clock = BeatClock(cfg.sound.tick_hz, self.sonification.on_beat, name="sonification")

        self.signal = Signal(cfg.mat)
        self.device: DeviceLink | None = None
        if not opts.virtual:
            self.device = opts.device or DeviceLink(self._on_raw_frame, port=opts.serial_port,
                                                    on_event=self._device_event)
        self.lights = LightEngine(cfg.light, self.light, send=self.device.send_leds if self.device else None)
        self.sonification.after_beat.append(self._publish_link_status)
        self._next_link_status = 0.0

        self.arrangements: dict[str, Arrangement] = {}
        self.refresh_catalog()
        self.store.subscribe(self._on_change)
        self.sonification.run_in_beat(self._apply_sound_settings)

        self.control = ControlContext(
            config=cfg, store=self.store, mat=self.perception.snapshot, virtual=self.virtual,
            play=self.play, settings=self.settings,
            streams={"leds": self.lights.preview, "levels": self.levels},
        )

    # ── 编排 ────────────────────────────────────────────────────────────

    def refresh_catalog(self) -> None:
        """重新读取全部编排，检查各自引用的素材是否齐全，写入状态中心供控制台列出。"""
        found, errors = discover(self.options.arrangements_dir)
        for e in errors:
            self.events.warning(e)
        self.arrangements = found
        items = []
        for a in found.values():
            missing: list[str] = []
            try:
                plan = self.sonification.prepare(a).plan
                missing = self.assets.missing(plan.assets)
                error = None
            except LoadError as e:
                error = str(e)
            items.append({
                "id": a.id, "title": a.title, "mode": a.mode, "modeLabel": a.mode_label,
                "description": a.description, "ringLabels": list(a.ring_labels),
                "missing": missing, "error": error,
            })
        self.store.set("catalog.arrangements", items)

    def play(self, arrangement_id: str) -> None:
        a = self.arrangements.get(arrangement_id)
        if a is None:
            raise LoadError(f"没有标识为 {arrangement_id} 的编排")
        self.switch(a)

    def switch(self, arrangement: Arrangement) -> None:
        """加载并切换到一份编排；加载失败时保持当前编排，抛出 ``LoadError``。"""
        try:
            inst = self.sonification.prepare(arrangement)
        except LoadError as e:
            self.events.error(f"无法加载 {arrangement.title}：{e}")
            raise
        self.sonification.switch(inst)

    def _acquire_assets(self, inst: ModeInstance, now: float) -> None:
        missing = self.assets.acquire(inst.id, inst.plan.assets, now)
        self.store.update({
            "status.audio.assets.missing": missing,
            "status.audio.assets.needed": len(inst.plan.assets),
            "status.audio.assets.state": self.assets.status(),
        })
        if missing:
            self.events.warning(f"{inst.arrangement.title}：缺少 {len(missing)} 个声音素材，用到它们的声音不会发声")

    # ── 设备与灯光 ──────────────────────────────────────────────────────

    def _on_raw_frame(self, frame: RawFrame) -> None:
        self.perception.feed(self.signal.pressure(frame.t, frame.seq, frame.values))

    def _device_event(self, level: str, text: str) -> None:
        getattr(self.events, level)(text)

    def _publish_link_status(self, now: float) -> None:
        if now >= self._next_levels and isinstance(self.backend, ScsynthBackend):
            self._next_levels = now + 0.1
            lv = self.backend.levels(self.engine.layout.azimuths, now)
            if lv is not None:
                self.levels.set(lv)
        if now < self._next_link_status:
            return
        self._next_link_status = now + 0.5
        if self.device is not None:
            st = self.device.status()
            st["source"] = "controller"
        else:
            st = {"connected": None, "port": None, "fps": None, "checksumErrors": None,
                  "problem": None, "source": "virtual"}
        self.store.update({"status.mat": st})

    # ── 设置 ────────────────────────────────────────────────────────────

    def _layout(self) -> SpeakerLayout:
        return SpeakerLayout.from_json(self.settings.get("sound.layout"))

    def _on_change(self, changes) -> None:
        paths = [p for p, _ in changes]
        if any(p.startswith("settings.sound") for p in paths):
            self.sonification.run_in_beat(self._apply_sound_settings)
        if "settings.run.soundLibrary" in paths:
            self.assets.set_root(Path(self.settings.get("run.soundLibrary")))
            self.refresh_catalog()

    def _apply_sound_settings(self, now: float) -> None:
        self.engine.set_master({"volume": float(self.settings.get("sound.volume", 0.8))}, now)
        layout = self._layout()
        orientation = float(self.settings.get("sound.orientation", 0.0))
        if layout != self.engine.layout or orientation != self.engine.orientation:
            self.engine.set_layout(layout, orientation, now)

    # ── 启动与停止 ──────────────────────────────────────────────────────

    def start(self) -> None:
        if self.virtual:
            self.virtual.start()
            log.info("使用虚拟垫子")
        elif self.device is not None:
            self.device.start()
        default = self.settings.get("run.defaultArrangement")
        first = default if default in self.arrangements else next(iter(self.arrangements), None)
        if first is None:
            self.events.error("没有可用的编排")
        else:
            if first != default:
                self.events.warning(f"默认编排 {default} 不存在，改用 {first}")
            try:
                self.play(first)
            except LoadError:
                pass
        self.clock.start()
        self.lights.start()

    def stop(self) -> None:
        self.lights.stop()
        self.clock.stop()
        if self.virtual:
            self.virtual.stop()
        if self.device is not None:
            self.device.stop()

    def now(self) -> float:
        return system_time()
