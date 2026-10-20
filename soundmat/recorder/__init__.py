"""录制：录下干净的声音并能和视频对齐（design/RECORDING.md、ARCHITECTURE「录制」）。

一次录制产生一个文件夹（以开始时间和编排命名）：

- ``master.wav``：总输出，声道数与音箱布局一致，24 位 WAV，由合成器服务在内部录下；
- ``stems/<总线>.wav``：每条环总线和分组总线一轨，加上共用效果的返回 ``fx``（可在设置里关闭）；
  分轨在模式总处理之前，可能超过 0 dBFS，用 32 位浮点 WAV；
- ``session.jsonl``：压力图（感知处理的每一帧）、垫面事件、声音意图、灯光，每行一条，带系统时间；
- ``info.json``：开始（即打板）的准确日期时间、编排与模式、开始时的设置、产出文件。

按下录制后灯环和控制台进入 3、2、1 的倒计时，这时还不录；倒计时结束的瞬间灯环整圈闪亮、
音箱在现场发出一声短促的提示音（打板），录音正好从这一刻开始。提示音只在现场响、不进录音
（见 ``ScsynthBackend.slate``），文件开头就是演奏；剪辑时把录音文件的开头对到视频里那一声上即可。
开始前检查剩余空间，录制中空间将尽时自动停止。录制的状态机在声音化的节拍线程里推进（``on_beat``），
但节拍线程从不读写存储卡：建文件夹在按下录制的那一刻、在调用方的线程里完成；会话数据、录制信息、
关闭文件和刷新录制列表都由这段录制自己的写文件线程（``SessionWriter``）完成。存储卡忙的时候
（例如刚发布完新版本，正在写回大量文件）一次建文件夹都可能卡住好几秒，放在节拍线程里会让演奏停顿。
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
from typing import TYPE_CHECKING, Callable

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

COUNTDOWN = 3.0             # 按下录制到打板（录音开始）的倒计时；这段时间也够合成器服务打开文件
FLASH = 0.25
MIN_FREE_SECONDS = 600      # 少于 10 分钟的空间：拒绝开始
STOP_FREE_SECONDS = 60      # 录制中少于 1 分钟的空间：自动停止
MARGIN_BYTES = 200 * 1024 * 1024
BYTES_PER_SAMPLE = {"master": 3, "stem": 4}   # 总输出 24 位，分轨 32 位浮点
SLATE_COLOR = (255, 246, 230)


class RecordingError(Conflict):
    """无法开始录制；消息直接显示给人看。"""


@dataclass
class Prepared:
    """按下录制时、在调用方线程里准备好的东西：文件夹已建好，写文件线程已开始。"""
    folder: Path
    started_wall: dt.datetime
    arrangement: dict
    files: dict[str, str]              # "master" 或分轨总线名 → 文件路径
    writer: "SessionWriter"


@dataclass
class Session:
    folder: Path
    countdown_t: float              # 按下录制、开始倒计时的系统时间
    start_t: float                  # 打板、录音开始的系统时间（倒计时结束）
    started_wall: dt.datetime
    arrangement: dict
    settings: dict
    channels: int
    files: list[str]
    audio: bool
    slate_done: bool = False
    stopped: str | None = None


class SessionWriter:
    """一段录制的写文件线程：按顺序把会话数据逐行写进 JSON Lines 文件，并执行交给它的文件操作
    （写录制信息、收尾）。调用方只往队列里放东西，从不等待存储卡。"""

    _CLOSE = object()

    def __init__(self, path: Path):
        self.path = path
        self.q: queue.Queue = queue.Queue()
        self.t = threading.Thread(target=self._run, name="session-writer", daemon=True)
        self.t.start()

    def put(self, record: dict) -> None:
        """追加一行会话数据。"""
        self.q.put(record)

    def call(self, fn: Callable[[], None]) -> None:
        """在写文件线程里执行一次文件操作（排在之前放进来的会话数据之后）。"""
        self.q.put(fn)

    def finish(self, then: Callable[[], None] | None = None) -> None:
        """写完已经放进来的内容后关闭文件，再执行 ``then``。不等待。"""
        if then is not None:
            self.q.put(self._CLOSE)
            self.q.put(then)
        self.q.put(None)

    def _run(self) -> None:
        f = open(self.path, "w", encoding="utf-8")
        try:
            while True:
                item = self.q.get()
                if item is None:
                    break
                if item is self._CLOSE:
                    f.close()
                elif callable(item):
                    try:
                        item()
                    except Exception:
                        log.exception("录制的文件操作出错")
                elif not f.closed:
                    f.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
        finally:
            f.close()


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
        # 逐帧取压力图。原来每拍读一次最新的快照、按节拍时刻限 30 次/秒：控制器约 28 帧/秒，两拍正好 1/30 秒，
        # 节拍时刻有零点几毫秒的抖动就常常要多等一拍，等的时候下一帧已经到了，模拟只录下约 23 帧/秒
        self.frame_queue = perception.frames.subscribe()
        self.led_count = config.light.led_count
        self.schedule_ahead = config.sound.schedule_ahead
        self.sample_rate = config.sound.expected_sample_rate
        self.session: Session | None = None
        self.writer: SessionWriter | None = None
        self._lock = threading.Lock()
        self._last_light_version = -1
        self._next_light = 0.0
        self._next_status = 0.0
        self._last_sound: dict | None = None
        self._was_audio_active = False
        self._starting = False             # 已经按下、还没在节拍线程里开始
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
        return Path(self.settings.get("recording.path"))      # 绝对路径，默认是数据目录下的 recordings/

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
        """检查空间，建好文件夹，再交给节拍线程开始倒计时。读写存储卡都在这里（调用方的线程）。"""
        with self._lock:
            if self.session is not None or self._starting:
                raise RecordingError("已经在录制")
            need = self.bytes_per_second() * MIN_FREE_SECONDS + MARGIN_BYTES
            free = self.free_bytes()
            if free < need:
                raise RecordingError(f"剩余空间 {free / 1e9:.1f} GB，不足以录制 10 分钟（需要约 {need / 1e9:.1f} GB）")
            if self.backend.records_audio and not self.backend.online:
                raise RecordingError("合成器服务没有响应，无法录音")
            self._starting = True
        try:
            prep = self._prepare()
        except Exception:
            with self._lock:
                self._starting = False
            raise
        self.sonification.run_in_beat(lambda now: self._begin(now, prep))

    def _prepare(self) -> Prepared:
        wall = dt.datetime.now().astimezone() + dt.timedelta(seconds=COUNTDOWN)
        arr = self._current_arrangement()
        folder = self.root / f"{wall:%Y-%m-%d_%H%M%S}_{arr.get('id') or 'none'}"
        folder.mkdir(parents=True, exist_ok=True)
        files = {"master": str(folder / "master.wav")}
        stems = self.backend.recordable_stems() if self.settings.get("recording.stems", True) else []
        if stems:                              # scsynth 不建目录，要先建好
            (folder / "stems").mkdir(exist_ok=True)
            for name in stems:
                files[name] = str(folder / "stems" / f"{name}.wav")
        return Prepared(folder, wall, arr, files, SessionWriter(folder / "session.jsonl"))

    def request_stop(self) -> None:
        self.sonification.run_in_beat(lambda now: self._end(now, "user"))

    # ── 节拍线程 ────────────────────────────────────────────────────────

    def _begin(self, now: float, prep: Prepared) -> None:
        start_t = now + COUNTDOWN
        started = self.backend.start_recording(prep.files, start_t)
        stems_dir = prep.folder / "stems"
        if not any(k != "master" for k in started):    # 一个分轨也没开始（例如没有合成器服务）：删掉空目录
            prep.writer.call(lambda: stems_dir.rmdir() if stems_dir.is_dir() else None)
        rel = [str(Path(prep.files[k]).relative_to(prep.folder)) for k in started]
        s = Session(folder=prep.folder, countdown_t=now, start_t=start_t, started_wall=prep.started_wall,
                    arrangement=prep.arrangement, settings=self.settings.snapshot(), channels=self._channels(),
                    files=rel + ["session.jsonl", "info.json"], audio=bool(started))
        with self._lock:
            self.session, self._starting = s, False
        self._was_audio_active = bool(started)
        self.backend.slate(start_t)        # 在 start_recording 之后：排在录音节点之后，不进录音
        self.writer = prep.writer
        self.writer.put({"t": _round(start_t), "type": "start", "arrangement": prep.arrangement})
        self._last_sound = None
        self._save_info(s)
        self.events.info(f"开始录制：{s.folder.name}" + ("" if started else "（没有合成器服务，只记录会话数据）"))
        self.on_beat(now, self.sonification.active.last if self.sonification.active else None)

    def _end(self, now: float, reason: str) -> None:
        s = self.session
        if s is None:
            return
        # 已经排好、还没响的声音也录进去；倒计时中停止时，录音节点还没开始，停止不能排在它前面
        self.backend.stop_recording(max(now + self.schedule_ahead, s.start_t))
        self.lights.set_system_layer("recording", None)
        s.stopped = reason
        if self.writer:
            self.writer.put({"t": _round(now), "type": "stop", "reason": reason})
            self._save_info(s, end_t=now)
            self.writer.finish(then=self.refresh_list)    # 写完、关闭后在写文件线程里刷新录制列表
            self.writer = None
        with self._lock:
            self.session = None
        self.state.set("status.recording", {"state": "idle"})
        text = {"user": "录制结束", "disk": "存储空间将尽，录制已自动停止",
                "synth": "合成器服务中断，录制已停止"}.get(reason, "录制结束")
        (self.events.warning if reason != "user" else self.events.info)(f"{text}：{s.folder.name}")

    def on_beat(self, now: float, output: BeatOutput | None) -> None:
        """每拍结束时由声音化调用：推进倒计时与打板，把这一拍的数据写进会话。"""
        s = self.session
        if s is None:
            self.event_queue.drain()
            self.frame_queue.drain()
            return
        el = now - s.countdown_t                 # 倒计时从按下开始，打板在 el = COUNTDOWN
        self._countdown_light(el)
        if not s.slate_done and el >= COUNTDOWN:
            s.slate_done = True
            self.writer.put({"t": _round(s.start_t), "type": "slate"})
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
                "elapsed": round(max(0.0, now - s.start_t), 1),
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
            rec = {"t": _round(e.t), "type": "event", "kind": e.kind, "zone": e.zone}
            if e.stone is not None:
                rec["stone"] = e.stone
            if e.from_zone is not None:
                rec["from"] = e.from_zone
            w.put(rec)
        for snap in self.frame_queue.drain():
            w.put({"t": _round(snap.t), "type": "pressure", "seq": snap.pressure.seq,
                   "values": [int(v * 1000 + 0.5) for v in snap.pressure.values.clip(0, 1)],
                   "occupied": sorted(snap.state.occupied),
                   # 每颗石头：[标识, 主区, 总压力（放下阈值为单位）]
                   "stones": [[s.id, s.zone, round(s.strength, 2)] for s in snap.state.stones]})
        if out is not None:
            sound = _sound_json(out.sound)
            if sound != self._last_sound:
                self._last_sound = sound
                w.put({"t": _round(now), "type": "sound", **sound})
            if out.sound.events:
                w.put({"t": _round(now), "type": "events",
                       "events": [{"id": e.id, "time": _round(now if e.time is None else e.time), "source": f"{e.source.kind}:{e.source.name}",
                                   "bus": e.bus, "params": {k: _round(x) for k, x in e.params.items()}}
                                  for e in out.sound.events]})
        light, lver = self.lights.preview.get_versioned()
        if light is not None and lver != self._last_light_version and now >= self._next_light:
            self._last_light_version = lver
            self._next_light = now + 0.1
            w.put({"t": _round(now), "type": "light", "colors": light["colors"]})

    # ── 文件 ────────────────────────────────────────────────────────────

    def _save_info(self, s: Session, end_t: float | None = None) -> None:
        """写录制信息（在写文件线程里）。内容此刻就算好，之后的变化不会影响它。"""
        info = self._info(s, end_t)
        path = s.folder / "info.json"
        self.writer.call(lambda: path.write_text(json.dumps(info, ensure_ascii=False, indent=2), "utf-8"))

    def _info(self, s: Session, end_t: float | None) -> dict:
        info = {
            "startedAt": s.started_wall.isoformat(timespec="milliseconds"),
            "startSystemTime": _round(s.start_t),
            # 录音文件从打板那一刻开始（提示音本身不在文件里，只在现场响、被摄像机录到）
            "slateOffsetSeconds": 0.0,
            "slateSystemTime": _round(s.start_t),
            # 会话数据里有确定时刻的声音（events 的 time、声部的开始时刻）比记下的时刻晚这么多响
            "scheduleAheadSeconds": self.schedule_ahead,
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
        return info

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

    def delete(self, name: str) -> None:
        """删除一段录制（整个文件夹），不可恢复。正在录的那一段不能删。"""
        folder = self.folder_of(name)
        with self._lock:
            s = self.session
            if s is not None and s.folder.resolve() == folder:
                raise RecordingError("这一段正在录制，停止后才能删除")
            shutil.rmtree(folder)
        self.refresh_list()
        self.events.info(f"删除了录制：{name}")

    def folder_of(self, name: str) -> Path:
        d = (self.root / name).resolve()
        if d.parent != self.root.resolve() or not (d / "info.json").is_file():
            raise NotFound("没有这段录制")
        return d
