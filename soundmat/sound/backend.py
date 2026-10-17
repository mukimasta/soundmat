"""声音引擎与合成器服务之间的接口。

引擎只通过 ``Backend`` 发出抽象指令；``RecordingBackend`` 是不发声的实现，照单记录所有指令，
用于测试和没有合成器服务的开发机（SOUND_ENGINE「测试替身」）。scsynth 的实现见 ``scsynth.py``。

所有指令都带执行时刻 ``at``（系统时间）。声部和混音结构的编号由引擎分配。
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from ..sonification.intent import Source
from .spatial import SpeakerGains


@dataclass
class BackendEvents:
    ended: list[int] = field(default_factory=list)   # 已经结束的声部编号
    restarted: bool = False                          # 合成器服务重新启动过


class Backend(Protocol):
    online: bool

    def create_mix(self, instance: str, buses: Sequence[str], channels: int, at: float,
                   fx: str | None = None) -> None: ...
    def set_mix_gain(self, instance: str, gain: float, fade: float, at: float) -> None: ...
    def free_mix(self, instance: str, at: float) -> None: ...
    def set_globals(self, instance: str, params: Mapping[str, float], at: float) -> None: ...

    def start_voice(self, node: int, instance: str, source: Source, bus: str,
                    params: Mapping[str, float], gains: SpeakerGains, fade_in: float,
                    at: float, oneshot: bool) -> None: ...
    def set_voice(self, node: int, params: Mapping[str, float], gains: SpeakerGains | None,
                  at: float) -> None: ...
    def release_voice(self, node: int, fade_out: float, at: float) -> None: ...
    def free_voice(self, node: int, at: float) -> None: ...

    def load_asset(self, ref: str, at: float) -> None: ...
    def free_asset(self, ref: str, at: float) -> None: ...

    def set_master(self, params: Mapping[str, float], at: float) -> None: ...
    def test_tone(self, channel: int, at: float) -> None: ...
    def recordable_stems(self) -> list[str]: ...
    def start_recording(self, files: Mapping[str, str], at: float) -> list[str]: ...
    def stop_recording(self, at: float) -> None: ...
    def recording_active(self) -> bool: ...
    def slate(self, at: float) -> None: ...

    def poll(self, now: float) -> BackendEvents: ...
    def flush(self) -> None: ...


@dataclass(frozen=True)
class Command:
    kind: str
    at: float
    args: dict[str, Any]


class RecordingBackend:
    """不发声的合成器服务替身：记录指令，并按时间模拟声部结束。

    - 淡出的声部在淡出时长之后结束；
    - 单次声音在 ``oneshot_length`` 秒后结束（真实长度只有合成器服务知道）；
    - 被强制释放的声部立即结束，不再通知。
    """

    def __init__(self, oneshot_length: float = 2.0):
        self.online = True
        self.oneshot_length = oneshot_length
        self.commands: list[Command] = []
        self._ends: list[tuple[float, int]] = []
        self._alive: set[int] = set()
        self._restart_pending = False

    # 测试辅助 ----------------------------------------------------------

    def of_kind(self, kind: str) -> list[Command]:
        return [c for c in self.commands if c.kind == kind]

    def clear(self) -> None:
        self.commands.clear()

    def simulate_restart(self) -> None:
        """模拟合成器服务崩溃后被系统守护重启：所有节点消失。"""
        self._alive.clear()
        self._ends.clear()
        self._restart_pending = True

    # Backend -------------------------------------------------------------

    def _rec(self, kind: str, at: float, **args) -> None:
        self.commands.append(Command(kind, at, args))

    def create_mix(self, instance, buses, channels, at, fx=None):
        self._rec("create_mix", at, instance=instance, buses=list(buses), channels=channels, fx=fx)

    def set_mix_gain(self, instance, gain, fade, at):
        self._rec("set_mix_gain", at, instance=instance, gain=gain, fade=fade)

    def free_mix(self, instance, at):
        self._rec("free_mix", at, instance=instance)

    def set_globals(self, instance, params, at):
        self._rec("set_globals", at, instance=instance, params=dict(params))

    def start_voice(self, node, instance, source, bus, params, gains, fade_in, at, oneshot):
        self._rec("start_voice", at, node=node, instance=instance, source=source, bus=bus,
                  params=dict(params), gains=list(gains.mono), stereo=(list(gains.left), list(gains.right)),
                  fade_in=fade_in, oneshot=oneshot)
        self._alive.add(node)
        if oneshot:
            heapq.heappush(self._ends, (at + self.oneshot_length, node))

    def set_voice(self, node, params, gains, at):
        self._rec("set_voice", at, node=node, params=dict(params),
                  gains=None if gains is None else list(gains.mono))

    def release_voice(self, node, fade_out, at):
        self._rec("release_voice", at, node=node, fade_out=fade_out)
        heapq.heappush(self._ends, (at + fade_out, node))

    def free_voice(self, node, at):
        self._rec("free_voice", at, node=node)
        self._alive.discard(node)

    def load_asset(self, ref, at):
        self._rec("load_asset", at, ref=ref)

    def free_asset(self, ref, at):
        self._rec("free_asset", at, ref=ref)

    def set_master(self, params, at):
        self._rec("set_master", at, params=dict(params))

    def test_tone(self, channel, at):
        self._rec("test_tone", at, channel=channel)

    def recordable_stems(self):
        return []

    def start_recording(self, files, at):
        self._rec("start_recording", at, files=dict(files))
        return []

    def stop_recording(self, at):
        self._rec("stop_recording", at)

    def recording_active(self):
        return False

    def slate(self, at):
        self._rec("slate", at)

    def flush(self):
        pass

    def poll(self, now):
        ev = BackendEvents(restarted=self._restart_pending)
        self._restart_pending = False
        while self._ends and self._ends[0][0] <= now:
            _, node = heapq.heappop(self._ends)
            if node in self._alive:
                self._alive.discard(node)
                ev.ended.append(node)
        return ev
