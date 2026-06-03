"""JamApp：Jam 模式主类。组装五层，跑高频主循环。

主循环（设计文档 §9，60Hz；Pi 部署降载，Mac 可再调高）：
  frame = sensor.latest(); delta = sensor_state.update(frame)
  依 R0/R1 控制值驱动开始/停止 + 全局 Lo-Fi（连续实时，不受扫描线影响）
  播放时：transport.advance → 伴奏（和声+鼓，按 16 分 tick）+ 扫描（命中石头触发旋律/bass）
  每帧渲染 LED
"""
from __future__ import annotations

import threading
import time

from .. import config
from ..core.osc import ADD_TO_HEAD, ADD_TO_TAIL
from ..core.services import SharedServices
from .bridge import MasterFX, SynthBridge
from .config_loader import JamConfig, load_jam_config
from .event import DrumEngine, EventEngine, HarmonyEngine, SensorState
from .led.renderer import JamLedRenderer
from .scheduler import ScanLine, SongPositionTracker, Transport
from .theory import Tempo, Tonality

LOOP_HZ = 60.0
# LED 物理刷新 30Hz 已经远超人眼分辨；jam-loop 跑 60Hz 的 Python 渲染浪费一半 CPU
# （profile：_render_led 占 _tick ~65%）。on_scan_hit / on_preview 仍每帧注入，只
# 节流贵的 108-LED 合成 + serial 写。
LED_HZ = 30.0
LED_PERIOD = 1.0 / LED_HZ
MASTER_SYNTH = "jam_master"
REVERB_BUS_SYNTH = "jam_reverb_bus"

# 默认总线增益（JAM_DESIGN §3/§6：和声 0.4、鼓 0.62 不变；旋律+bass 总线略抬）
MELODY_BUS_GAIN = 0.9
HARMONY_BUS_GAIN = 0.4
# web drumGain=0.48；SC 鼓 SynthDef peak 偏低，总线略抬以对齐听感
DRUM_BUS_GAIN = 0.62


class JamApp:
    def __init__(self, manifest: dict, services: SharedServices):
        self.services = services
        self.manifest = manifest
        self.cfg: JamConfig = load_jam_config(manifest)

        # 理论层
        self.tempo = Tempo(self.cfg.bpm)
        self.tonality = Tonality(self.cfg.key, self.cfg.scale)
        self.timing = self.cfg.timing

        # 调度层
        self.song_pos = SongPositionTracker(self.cfg.progression, self.timing)
        self.scanline = ScanLine(self.timing)
        self.drum = DrumEngine(self.cfg.drum_patterns, self.cfg.drum_sequence,
                               self.timing.bars_per_harmony_cycle)
        self.transport = Transport(self.cfg.bpm, self.drum.total_bars)

        # 事件层
        self.sensor_state = SensorState()
        self.harmony = HarmonyEngine(self.song_pos, self.cfg.chord_voicings, self.drum.total_bars)
        self.event_engine = EventEngine(self.timing, self.cfg.rings,
                                        self.cfg.trigger_tables, self.song_pos)

        # LED
        self.led = JamLedRenderer(self.cfg.rings)

        # 桥层（start 时建，需 group）
        self.group: int | None = None
        self.harmony_group: int | None = None
        self.master_node: int | None = None
        self.reverb_bus_node: int | None = None
        self.bridge: SynthBridge | None = None
        self.master_fx: MasterFX | None = None

        # 运行时
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_control_active = False
        self._control_inactive_since: float | None = None
        self._last_control_value = 0.0
        self._last_control_count = 0
        self._last_led_render = 0.0
        self._lock = threading.Lock()

    # ── 生命周期 ──
    def start(self) -> None:
        if self._thread is not None:
            return
        sc = self.services.sc
        self.group = sc.new_group()
        self.harmony_group = sc.new_group(target=self.group, add_action=ADD_TO_HEAD)
        # 共享 reverb：voices(HEAD) → harmony_group → jam_reverb_bus → jam_master(TAIL)
        # 先 add reverb_bus（TAIL），再 add master（TAIL）→ master 排在 reverb_bus 之后，
        # 这样 voice 写入 send 总线后，同一 control block 内 reverb_bus 读到，master 再读
        # MELODY_BUS 已含 reverb tail。
        self.reverb_bus_node = self.services.osc.new_synth(
            REVERB_BUS_SYNTH,
            {
                "in": config.JAM_REVERB_BUS,
                "out": config.MELODY_BUS,
                "decay": 1.4,
                "preDelay": 0.02,
                "amp": 1.0,
            },
            target=self.group, add_action=ADD_TO_TAIL,
        )
        # master synth 挂在 group 尾部，读三条总线
        self.master_node = self.services.osc.new_synth(
            MASTER_SYNTH,
            {
                "melodyBus": config.MELODY_BUS, "harmonyBus": config.HARMONY_BUS,
                "drumBus": config.DRUM_BUS,
                "melodyGain": MELODY_BUS_GAIN, "harmonyGain": HARMONY_BUS_GAIN,
                "drumGain": DRUM_BUS_GAIN,
                "cutoff": 14000.0, "drive": 0.0, "lofiGain": 1.0,
                "amp": self.cfg.master_volume,
                "out": config.OUT_BUS,
            },
            target=self.group, add_action=ADD_TO_TAIL,
        )
        self.bridge = SynthBridge(
            self.services.osc, self.group, self.cfg.rings, self.tonality,
            harmony_group=self.harmony_group,
        )
        self.master_fx = MasterFX(self.services.osc, self.master_node,
                                  self.cfg.lofi_mapping or None, self.cfg.master_volume)

        self.transport.reset()
        self.scanline.reset()
        self.event_engine.reset()
        self.sensor_state.reset()
        self._control_inactive_since = None
        self._last_control_active = False

        self._last_led_render = 0.0
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="jam-loop")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self.services.leds.clear()
        if self.group is not None:
            self.services.sc.free_group(self.group)
            self.group = None
            self.harmony_group = None
            self.master_node = None
            self.reverb_bus_node = None
            self.bridge = None
            self.master_fx = None

    # ── 主循环 ──
    def _fire_downbeat(self) -> None:
        """开拍瞬间补发 t=0 的和声 bar0 + 鼓 step0（sixteenth_ticks 不含 i=0）。"""
        assert self.bridge is not None
        for ev in self.harmony.emit(-1e-9, 0.0, self.tempo):
            self.bridge.handle(ev)
        for ev in self.drum.emit(-1e-9, 0.0, self.tempo):
            self.bridge.handle(ev)

    def _run(self) -> None:
        period = 1.0 / LOOP_HZ
        last = time.monotonic()
        while not self._stop.is_set():
            now = time.monotonic()
            dt = min(max(now - last, 0.0), 0.05)
            last = now
            try:
                self._tick(now, dt)
            except Exception as e:  # 一帧出错不崩主循环
                print(f"[jam] tick error: {e}")
            time.sleep(max(0.0, period - (time.monotonic() - now)))

    def _effective_control_active(self, raw_active: bool, now: float) -> bool:
        """控制石 raw 消失后 hold CONTROL_RELEASE_HOLD_SEC 再判 inactive。"""
        hold = config.CONTROL_RELEASE_HOLD_SEC
        if raw_active:
            self._control_inactive_since = None
            return True
        if self._control_inactive_since is None:
            if self._last_control_active:
                self._control_inactive_since = now
                return True
            return False
        if (now - self._control_inactive_since) < hold:
            return True
        self._control_inactive_since = None
        return False

    def _tick(self, now: float, dt: float) -> None:
        assert self.bridge is not None and self.master_fx is not None
        frame = self.services.sensor.latest()
        if frame is None:
            self._render_led(now)
            return
        delta = self.sensor_state.update(frame.matrix)
        self._last_control_value = delta.control_value
        self._last_control_count = delta.control_count

        # 全局 Lo-Fi：连续实时，不受扫描线影响
        self.master_fx.set_lofi(delta.control_value)

        control_active = self._effective_control_active(delta.control_active, now)

        if not control_active:
            # 0 颗控制石：静止 + 全局 reset（仅在 active→inactive 边沿）
            if self._last_control_active or self.transport.musical_time > 0 or self.transport.form_ended:
                self.transport.reset()
                self.scanline.reset()
                self.event_engine.reset()
                self.bridge._release_pad()
            self._last_control_active = False
            # 空闲：放石 preview
            self._handle_placed_preview(delta, now, 0)
            self._render_led(now, delta)
            return

        # control_active
        if not self.transport.form_ended:
            new_start = self.transport.start()
            if new_start:
                self._fire_downbeat()
        self._last_control_active = True

        if not self.transport.playing:
            # 曲终态：不推进，等清空 R0/R1
            self._render_led(now, delta)
            return

        # 播放推进
        prev_t, curr_t, _ended = self.transport.advance(dt)

        for ev in self.harmony.emit(prev_t, curr_t, self.tempo):
            self.bridge.handle(ev)
        for ev in self.drum.emit(prev_t, curr_t, self.tempo):
            self.bridge.handle(ev)

        prev_a, curr_a, did_wrap = self.scanline.update(curr_t, self.cfg.bpm)
        loop_rot = self.scanline.loop_rotation

        if config.JAM_LOOP_PLACE_PREVIEW_VEL > 0:
            self._handle_placed_preview(delta, now, loop_rot)

        notes = self.event_engine.emit_sweep(
            prev_a, curr_a, did_wrap, delta.occupied, now, loop_rot, self.tonality,
            sec_per_quarter=self.tempo.sec_per_quarter,
        )
        if did_wrap and self.timing.is_two_bar:
            self.scanline.loop_rotation = (loop_rot + 1) % 4
        for ev in notes:
            self.bridge.handle(ev)
            self.led.on_scan_hit(ev.source_slice, ev.ring, now)

        self._render_led(now, delta)

    def _handle_placed_preview(self, delta, now: float, loop_rotation: int) -> None:
        assert self.bridge is not None
        playing = self.transport.playing
        preview_vel = config.JAM_LOOP_PLACE_PREVIEW_VEL if playing else config.JAM_IDLE_PLACE_PREVIEW_VEL
        for ring, slc in delta.placed:
            note = self.event_engine.preview(
                ring, slc, loop_rotation, self.tonality,
                sec_per_quarter=self.tempo.sec_per_quarter,
                velocity=preview_vel,
            )
            if note is None:
                continue
            self.bridge.handle_note(note)
            self.led.on_preview(slc, ring, now)
            if playing:
                self.event_engine.mark_triggered(ring, slc, now)

    def _trigger_stones(self, delta):
        return [(r, s) for (r, s) in delta.occupied
                if (c := self.cfg.rings.get(r)) is not None and c.is_trigger]

    def _render_led(self, now: float, delta=None) -> None:
        # 节流到 LED_HZ（30）。短效注入（on_scan_hit / on_preview）仍每帧执行，
        # 仅跳过 108-LED 合成 + 串口写；下次开闸时一次性反映最新状态。
        if now - self._last_led_render < LED_PERIOD:
            return
        self._last_led_render = now
        stones = self._trigger_stones(delta) if (delta is not None and self.transport.playing) else []
        control_count = delta.control_count if delta is not None else 0
        buf = self.led.render(
            now,
            sweep_angle=self.scanline.curr_angle,
            playing=self.transport.playing,
            form_ended=self.transport.form_ended,
            control_count=control_count,
            stones=stones,
        )
        self.services.leds.set_buffer(buf)

    # ── ModeApp 协议 ──
    def status(self) -> dict:
        pos = self.song_pos.position_at(self.transport.musical_time, self.cfg.bpm)
        symbol, _idx, _bar = self.song_pos.harmony_for_bar(pos.bar_global)
        return {
            "mode": "jam",
            "name": self.cfg.name,
            "bpm": self.cfg.bpm,
            "key": self.cfg.key,
            "scale": self.cfg.scale,
            "playing": self.transport.playing,
            "form_ended": self.transport.form_ended,
            "musical_time": round(self.transport.musical_time, 2),
            "form_duration": round(self.transport.form_duration, 2),
            "chord": symbol,
            "chord_index": pos.chord_idx,
            "bar_global": pos.bar_global,
            "control_count": self._last_control_count,
            "lofi": round(self._last_control_value),
            "occupied": sorted(self.sensor_state.occupied),
            "master_volume": self.cfg.master_volume,
        }

    def set_param(self, key: str, value) -> None:
        if key == "bpm":
            self.cfg.bpm = float(value)
            self.tempo = Tempo(self.cfg.bpm)
            self.transport.set_bpm(self.cfg.bpm)
        elif key == "master_volume":
            self.cfg.master_volume = float(value)
            if self.master_fx is not None:
                self.master_fx.set_volume(self.cfg.master_volume)
        elif key == "key":
            self.cfg.key = str(value)
            self.tonality = Tonality(self.cfg.key, self.cfg.scale)
            if self.bridge is not None:
                self.bridge.set_tonality(self.tonality)
        elif key == "scale":
            self.cfg.scale = str(value)
            self.tonality = Tonality(self.cfg.key, self.cfg.scale)
            if self.bridge is not None:
                self.bridge.set_tonality(self.tonality)
