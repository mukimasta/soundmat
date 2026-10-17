import time

from soundmat.clock import Beat, BeatClock
from soundmat.supervisor import Options, Supervisor

from helpers import EchoMode, arrangement


def test_beat_window():
    assert Beat(3, 10.0, 1 / 60).window(0.1) == (10.0, 10.1)


def test_clock_ticks_and_survives_exceptions():
    beats = []

    def on_beat(b):
        beats.append(b)
        if len(beats) == 2:
            raise RuntimeError("one bad beat")

    c = BeatClock(200, on_beat)
    c.start()
    time.sleep(0.2)
    c.stop()
    assert len(beats) > 10
    assert [b.index for b in beats] == list(range(len(beats)))
    assert all(b2.t > b1.t for b1, b2 in zip(beats, beats[1:]))


def test_running_supervisor_end_to_end(config):
    sup = Supervisor(config, Options(virtual=True, modes={"echo": EchoMode}))
    sup.switch(arrangement())
    sup.start()
    try:
        sup.virtual.toggle(60)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not sup.backend.of_kind("start_voice"):
            time.sleep(0.02)
    finally:
        sup.stop()
    assert sup.backend.of_kind("start_voice")
