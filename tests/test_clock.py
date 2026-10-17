import time

from soundmat.clock import Beat, BeatClock


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


def test_running_supervisor_end_to_end(make_sup, tmp_path):
    sup = make_sup(modes={"echo": EchoMode}, arrangements_dir=tmp_path / "none")
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



def test_beat_lag_and_stalls_are_measured():
    """节拍延迟：比计划晚开始多久；超过 stall_after 计为一次卡住，最近 1 分钟的最大值可读。"""
    import time
    from soundmat.clock import BeatClock

    slow = {"n": 0}

    def on_beat(beat):
        slow["n"] += 1
        if slow["n"] == 5:
            time.sleep(0.08)                    # 一拍算了 80 ms：下一拍至少晚 60 ms

    clk = BeatClock(60, on_beat, stall_after=0.05)
    clk.start()
    time.sleep(0.4)
    clk.stop()
    assert clk.stalls >= 1
    assert clk.max_lag() >= 0.05
    assert clk.overruns >= 1
