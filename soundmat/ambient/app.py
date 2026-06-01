"""AmbientApp：Ambient 模式主类。

信号链（与 sonification/soundmat/app.py 对齐）：
  源（ADD_TO_HEAD） → reverb（ADD_TO_TAIL） → master（ADD_TO_TAIL）
  sources 干声 out=2（MIX_BUS），reverb aux out=8（REVERB_BUS）→
  reverb 读 8 输出到 2 → master 读 2 输出到 0（硬件）。

主循环 20Hz：sensor → tracker → state → mapper → voices.reconcile + pump → LED。
"""
from __future__ import annotations

import threading
import time

from ..core.osc import ADD_TO_TAIL
from ..core.services import SharedServices
from .buffers import BufferPool
from .led import render as render_led
from .mapping import KyotoMapper
from .state import StateModel
from .tracker import Tracker
from .voices import VoicePool

LOOP_HZ = 20.0


class AmbientApp:
    def __init__(self, manifest: dict, services: SharedServices):
        self.services = services
        self.manifest = manifest
        self.name = manifest.get("name", "Ambient")
        self.tracker = Tracker()
        self.state_model = StateModel()
        self.mapper = KyotoMapper(manifest)
        self.group: int | None = None
        self.voices: VoicePool | None = None
        self._reverb_node: int | None = None
        self._master_node: int | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread is not None:
            return
        self.group = self.services.sc.new_group()
        # 加载 buffer
        buffers = BufferPool(self.services.sc)
        buffers.load_manifest(self.manifest)
        # 持久 FX 链：reverb → master，ADD_TO_TAIL（排在源之后）
        osc = self.services.osc
        self._reverb_node = osc.new_synth("reverb", {}, target=self.group, add_action=ADD_TO_TAIL)
        self._master_node = osc.new_synth("master", {}, target=self.group, add_action=ADD_TO_TAIL)
        self.voices = VoicePool(osc, self.group, buffers)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ambient-loop")
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
            self.voices = None
            self._reverb_node = None
            self._master_node = None

    def _run(self) -> None:
        period = 1.0 / LOOP_HZ
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                frame = self.services.sensor.latest()
                if frame is not None:
                    occ = self.tracker.occupied(frame.matrix)
                    state, events = self.state_model.update(occ)
                    if self.voices is not None:
                        result = self.mapper.map(state, events)
                        self.voices.reconcile(result)
                        self.voices.pump(t0)
                    self.services.leds.set_buffer(render_led(t0, occ))
            except Exception as e:
                print(f"[ambient] tick error: {e}")
            time.sleep(max(0.0, period - (time.monotonic() - t0)))

    # ── ModeApp 协议 ──────────────────────────────────────────────────────

    def status(self) -> dict:
        return {
            "mode": "ambient",
            "name": self.name,
            "occupied": len(self.state_model.state.occupied),
        }

    def set_param(self, key: str, value) -> None:
        pass
