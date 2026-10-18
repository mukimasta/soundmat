"""测试用的模式和工具。"""
from __future__ import annotations

from soundmat.clock import Beat
from soundmat.intent import BeatOutput, Event, ModeStatus, SoundIntent, Source, Voice
from soundmat.sonification.mode import Arrangement, LoadError, LoadPlan, Mode


class EchoMode(Mode):
    """每颗石头一个持续声部；每个放下事件一个立即的单次声音。"""
    name = "echo"

    def load(self):
        if self.arrangement.content.get("broken"):
            raise LoadError("编排缺少必需的内容")
        ctrl = frozenset(self.arrangement.content.get("control", ()))
        return LoadPlan(control_zones=ctrl, assets=frozenset(self.arrangement.content.get("assets", ())))

    def start(self, t):
        self.started = t
        self.fail = False

    def tick(self, beat: Beat, snapshot, events):
        if getattr(self, "fail", False):
            raise RuntimeError("boom")
        src = Source("instrument", self.arrangement.content.get("synth", "pad"))
        voices = tuple(Voice(f"z{z}", src, "ring0") for z in sorted(snapshot.state.occupied))
        evs = tuple(Event(f"{e.zone}@{e.t}", beat.t, src, "ring1") for e in events if e.kind == "place")
        return BeatOutput(SoundIntent(voices, evs), status=ModeStatus(text=f"{len(voices)} 颗"))


def arrangement(id="echo", **content):
    return Arrangement(id=id, title=id.upper(), mode="echo", content=content)


def beat(i, t):
    return Beat(i, t, 1 / 60)
