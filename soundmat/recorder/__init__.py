"""录制：录下干净的声音并能和视频对齐（design/RECORDING.md、ARCHITECTURE「录制」）。

一次录制产生一个文件夹（以开始时间和编排命名）：

- ``master.wav``：总输出，声道数与音箱布局一致，24 位 WAV，由合成器服务在内部录下；
- ``stems/<总线>.wav``：每条环总线和分组总线一轨，加上共用效果的返回 ``fx``（可在设置里关闭）；
  分轨在模式总处理之前，可能超过 0 dBFS，用 32 位浮点 WAV；
- ``session.jsonl``：压力图、垫面事件、声音意图、灯光，每行一条，带系统时间；
- ``info.json``：开始的准确日期时间、打板在录音中的位置、编排与模式、开始时的设置、产出文件。

按下录制后录音立即开始，灯环和控制台同时进入 3、2、1 的倒计时；倒计时结束的瞬间灯环整圈闪亮、
音箱发出一声短促的提示音，这一刻（打板）记进录制信息和会话数据。开始前检查剩余空间，录制中
空间将尽时自动停止。录制的状态机在声音化的节拍线程里推进（``on_beat``）。
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import queue
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from ..config import Config
from ..errors import Conflict, NotFound
from ..intent import BeatOutput, LightLayer, SoundIntent
from ..monitor.log import EventLog
from ..store import Store
from ..store.settings import Settings

if TYPE_CHECKING:
    from ..light import LightEngine
    from ..perception import Perception
    from ..sonification import Sonification

log = logging.getLogger("soundmat.recorder")

START_DELAY = 0.2           # 录音在请求后这么久开始（让合成器服务打开文件）
COUNTDOWN = 3.0
FLASH = 0.25
MIN_FREE_SECONDS = 600      # 少于 10 分钟的空间：拒绝开始
STOP_FREE_SECONDS = 60      # 录制中少于 1 分钟的空间：自动停止
MARGIN_BYTES = 200 * 1024 * 1024
BYTES_PER_SAMPLE = {"master": 3, "stem": 4}   # 总输出 24 位，分轨 32 位浮点
SLATE_COLOR = (255, 246, 230)


class RecordingError(Conflict):
    """无法开始录制；消息直接显示给人看。"""


@dataclass
class Session:
    folder: Path
    start_t: float                  # 录音开始的系统时间
    started_wall: dt.datetime
    arrangement: dict
    settings: dict
    channels: int
    files: list[str]
    audio: bool
    slate_done: bool = False
    stopped: str | None = None


class SessionWriter:
    """后台线程把会话数据逐行写进 JSON Lines 文件，不阻塞节拍线程。"""

    def __init__(self, path: Path):
        self.q: queue.Queue = queue.Queue()
        self.f = open(path, "w", encoding="utf-8")
        self.t = threading.Thread(target=self._run, name="session-writer", daemon=True)
        self.t.start()

    def put(self, record: dict) -> None:
        self.q.put(record)

    def close(self) -> None:
        self.q.put(None)
        self.t.join(timeout=5)
        self.f.close()

    def _run(self) -> None:
        while True:
            rec = self.q.get()
            if rec is None:
                break
            self.f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")


def _round(x: float, n: int = 4) -> float:
    return round(float(x), n)


def _sound_json(intent: SoundIntent) -> dict:
    def pos(p):
        return None if p is None else [_round(p.angle, 2), _round(p.radius, 3)]
    return {
        "voices": [{"id": v.id, "source": f"{v.source.kind}:{v.source.name}", "bus": v.bus,
                    "params": {k: _round(x) for k, x in v.params.items()}, "position": pos(v.position)}
                   for v in intent.voices],
        "globals": {k: _round(x) for k, x in intent.globals.items()},
    }


class Recorder:
    def __init__(self, store: Store, events: EventLog, settings: Settings, sonification: "Sonification",
                 perception: "Perception", lights: "LightEngine", config: Config):
        self.state = store.writer("status.recording", "catalog.recordings")
        self.events = events
        self.settings = settings
        self.sonification = sonification
        self.backend = sonification.engine.backend
        self.perception = perception
        self.lights = lights
        self.event_queue = perception.events.subscribe()
        self.led_count = config.light.led_count
        self.latency = config.sound.output_latency
        self.sample_rate = config.sound.expected_sample_rate
        self.session: Session | None = None
        self.writer: SessionWriter | None = None
        self._lock = threading.Lock()
        self._last_snap_version = -1
        self._last_light_version = -1
        self._next_pressure = 0.0
        self._next_light = 0.0
        self._next_status = 0.0
        self._last_sound: dict | None = None
        self._was_audio_active = False
        self.state.set("status.recording", {"state": "idle"})
        self.refresh_list()
        sonification.after_beat.append(self.on_beat)
        store.subscribe(self._on_change)

    def _on_change(self, changes) -> None:
        if any(path == "settings.recording.path" for path, _ in changes):
            self.refresh_list()

    def _channels(self) -> int:
        return self.sonification.engine.layout.channels

    def _current_arrangement(self) -> dict:
        a = self.sonification.active
        if a is None:
            return {}
        return {"id": a.arrangement.id, "title": a.arrangement.title, "mode": a.arrangement.mode}

    # ── 位置与空间 ──────────────────────────────────────────────────────

    @property
    def root(self) -> Path:
        return Path(self.settings.get("recording.path", "data/recordings"))

    def bytes_per_second(self, stems: int | None = None) -> int:
        """录音每秒写多少字节（总输出加分轨）；不录音频时为 0。"""
        if not (self.backend.records_audio and self.backend.online):
            return 0
        if stems is None:
            stems = len(self.backend.recordable_stems()) if self.settings.get("recording.stems", True) else 0
        per_frame = BYTES_PER_SAMPLE["master"] + stems * BYTES_PER_SAMPLE["stem"]
        return self.sample_rate * self._channels() * per_frame

    def free_bytes(self) -> int:
        p = self.root
        while not p.exists() and p != p.parent:
            p = p.parent
        return shutil.disk_usage(p).free

    # ── 命令（任意线程）─────────────────────────────────────────────────

    def request_start(self) -> None:
        with self._lock:
            if self.session is not None:
                raise RecordingError("已经在录制")
            need = self.bytes_per_second() * MIN_FREE_SECONDS + MARGIN_BYTES
            free = self.free_bytes()
            if free < need:
                raise RecordingError(f"剩余空间 {free / 1e9:.1f} GB，不足以录制 10 分钟（需要约 {need / 1e9:.1f} GB）")
            if self.backend.records_audio and not self.backend.online:
                raise RecordingError("合成器服务没有响应，无法录音")
        self.sonification.run_in_beat(self._begin)

    def request_stop(self) -> None:
        self.sonification.run_in_beat(lambda now: self._end(now, "user"))

    # ── 节拍线程 ────────────────────────────────────────────────────────

    def _begin(self, now: float) -> None:
        if self.session is not None:
            return
        start_t = now + START_DELAY
        wall = dt.datetime.now().astimezone() + dt.timedelta(seconds=START_DELAY)
        arr = self._current_arrangement()
        folder = self.root / f"{wall:%Y-%m-%d_%H%M%S}_{arr.get('id') or 'none'}"
        folder.mkdir(parents=True, exist_ok=True)
        files = {"master": str(folder / "master.wav")}
        stems_dir = folder / "stems"
        stems = self.backend.recordable_stems() if self.settings.get("recording.stems", True) else []
        if stems:                              # scsynth 不建目录，要先建好；没有音频时不建
            stems_dir.mkdir(exist_ok=True)
            for name in stems:
                files[name] = str(stems_dir / f"{name}.wav")
        started = self.backend.start_recording(files, start_t)
        if stems and not set(stems) & set(started):
            stems_dir.rmdir()                  # 合成器服务离线，一个分轨也没开始
        rel = [str(Path(files[k]).relative_to(folder)) for k in started]
        self.session = Session(folder=folder, start_t=start_t, started_wall=wall, arrangement=arr,
                               settings=self.settings.snapshot(), channels=self._channels(),
                               files=rel + ["session.jsonl", "info.json"], audio=bool(started))
        self._was_audio_active = bool(started)
        self.backend.slate(start_t + COUNTDOWN)
        self.writer = SessionWriter(folder / "session.jsonl")
        self.writer.put({"t": _round(start_t), "type": "start", "arrangement": arr})
        self._last_snap_version = -1
        self._last_sound = None
        self._write_info()
        self.events.info(f"开始录制：{folder.name}" + ("" if started else "（没有合成器服务，只记录会话数据）"))
        self.on_beat(now, self.sonification.active.last if self.sonification.active else None)

    def _end(self, now: float, reason: str) -> None:
        s = self.session
        if s is None:
            return
        self.backend.stop_recording(now + self.latency)
        self.lights.set_system_layer("recording", None)
        s.stopped = reason
        if self.writer:
            self.writer.put({"t": _round(now), "type": "stop", "reason": reason})
            self.writer.close()
            self.writer = None
        self._write_info(end_t=now)
        self.session = None
        self.state.set("status.recording", {"state": "idle"})
        self.refresh_list()
        text = {"user": "录制结束", "disk": "存储空间将尽，录制已自动停止",
                "synth": "合成器服务中断，录制已停止"}.get(reason, "录制结束")
        (self.events.warning if reason != "user" else self.events.info)(f"{text}：{s.folder.name}")

    def on_beat(self, now: float, output: BeatOutput | None) -> None:
        """每拍结束时由声音化调用：推进倒计时与打板，把这一拍的数据写进会话。"""
        s = self.session
        if s is None:
            self.event_queue.drain()
            return
        el = now - s.start_t
        self._countdown_light(el)
        if not s.slate_done and el >= COUNTDOWN:
            s.slate_done = True
            self.writer.put({"t": _round(s.start_t + COUNTDOWN), "type": "slate"})
        self._record_data(now, output)
        if s.audio and self._was_audio_active and not self.backend.recording_active():
            self._end(now, "synth")
            return
        if now >= self._next_status:
            self._next_status = now + 0.5
            if el > COUNTDOWN and s.audio:
                stems = len(s.files) - 3
                if self.free_bytes() < self.bytes_per_second(stems) * STOP_FREE_SECONDS + 50 * 1024 * 1024:
                    self._end(now, "disk")
                    return
            state = "countdown" if el < COUNTDOWN else "recording"
            self.state.set("status.recording", {
                "state": state,
                "count": max(1, 3 - int(max(0.0, el))) if el < COUNTDOWN else None,
                "elapsed": round(max(0.0, el), 1),
                "flash": COUNTDOWN <= el < COUNTDOWN + FLASH,
                "folder": s.folder.name,
                "audio": s.audio,
                "freeGB": round(self.free_bytes() / 1e9, 1),
            })
        if el < COUNTDOWN + FLASH:
            # 倒计时期间每拍更新，保证数字准时
            self._next_status = min(self._next_status, now + 0.05)

    def _countdown_light(self, el: float) -> None:
        n = self.led_count
        if el >= COUNTDOWN + FLASH:
            self.lights.set_system_layer("recording", None)
            return
        rgb = np.tile(np.array(SLATE_COLOR, dtype=np.float32) / 255, (n, 1))
        alpha = np.zeros(n, dtype=np.float32)
        if el >= COUNTDOWN:
            alpha[:] = 1.0                       # 打板：整圈全亮
        elif el >= 0:
            lit = 3 - int(el)                    # 三段全亮，每秒熄灭一段
            alpha[: lit * n // 3] = 0.9
        self.lights.set_system_layer("recording", LightLayer("recording", 1000, rgb, alpha))

    def _record_data(self, now: float, out: BeatOutput | None) -> None:
        w = self.writer
        if w is None:
            return
        for e in self.event_queue.drain():
            w.put({"t": _round(e.t), "type": "event", "kind": e.kind, "zone": e.zone})
        snap, ver = self.perception.snapshot.get_versioned()
        if snap is not None and ver != self._last_snap_version and now >= self._next_pressure:
            self._last_snap_version = ver
            self._next_pressure = now + 1 / 30
            w.put({"t": _round(snap.t), "type": "pressure", "seq": snap.pressure.seq,
                   "values": [int(v * 1000 + 0.5) for v in snap.pressure.values.clip(0, 1)],
                   "occupied": sorted(snap.state.occupied)})
        if out is not None:
            sound = _sound_json(out.sound)
            if sound != self._last_sound:
                self._last_sound = sound
                w.put({"t": _round(now), "type": "sound", **sound})
            if out.sound.events:
                w.put({"t": _round(now), "type": "events",
                       "events": [{"id": e.id, "time": _round(e.time), "source": f"{e.source.kind}:{e.source.name}",
                                   "bus": e.bus, "params": {k: _round(x) for k, x in e.params.items()}}
                                  for e in out.sound.events]})
        light, lver = self.lights.preview.get_versioned()
        if light is not None and lver != self._last_light_version and now >= self._next_light:
            self._last_light_version = lver
            self._next_light = now + 0.1
            w.put({"t": _round(now), "type": "light", "colors": light["colors"]})

    # ── 文件 ────────────────────────────────────────────────────────────

    def _write_info(self, end_t: float | None = None) -> None:
        s = self.session
        info = {
            "startedAt": s.started_wall.isoformat(timespec="milliseconds"),
            "startSystemTime": _round(s.start_t),
            "slateOffsetSeconds": COUNTDOWN,
            "slateSystemTime": _round(s.start_t + COUNTDOWN),
            "arrangement": s.arrangement,
            "channels": s.channels,
            "sampleRate": self.sample_rate,
            "format": "WAV：总输出 24 位整数，分轨 32 位浮点",
            "audio": s.audio,
            "files": s.files,
            "settings": s.settings,
        }
        if end_t is not None:
            info["duration"] = round(max(0.0, end_t - s.start_t), 2)
            info["endedAt"] = (s.started_wall + dt.timedelta(seconds=info["duration"])).isoformat(timespec="milliseconds")
            info["stopReason"] = s.stopped
        (s.folder / "info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), "utf-8")

    def list(self) -> list[dict]:
        items = []
        root = self.root
        if not root.is_dir():
            return items
        for d in sorted(root.iterdir(), reverse=True):
            info_path = d / "info.json"
            if not info_path.is_file():
                continue
            try:
                info = json.loads(info_path.read_text("utf-8"))
            except (OSError, ValueError):
                continue
            items.append({"name": d.name, "startedAt": info.get("startedAt"),
                          "title": (info.get("arrangement") or {}).get("title", ""),
                          "duration": info.get("duration"), "audio": info.get("audio", False)})
        return items

    def refresh_list(self) -> None:
        self.state.set("catalog.recordings", self.list())

    def folder_of(self, name: str) -> Path:
        d = (self.root / name).resolve()
        if d.parent != self.root.resolve() or not (d / "info.json").is_file():
            raise NotFound("没有这段录制")
        return d
