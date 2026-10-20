import time

from soundmat.perception import Perception
from soundmat.perception.virtual import VirtualMat


def test_virtual_click_flows_through_debounce(config):
    p = Perception(config.mat, source="virtual")
    events = p.events.subscribe()
    vm = VirtualMat(p.feed)
    assert vm.toggle(40) is True
    p.feed(vm.frame(t=0.0))
    assert events.drain() == []          # 去抖期内还不算放下
    p.feed(vm.frame(t=0.09))
    ev = events.drain()
    assert [(e.kind, e.zone) for e in ev] == [("place", 40)]
    snap = p.snapshot.get()
    assert snap.source == "virtual" and snap.state.occupied == {40}
    assert vm.toggle(40) is False
    p.feed(vm.frame(t=0.1))
    p.feed(vm.frame(t=0.2))
    assert [e.kind for e in events.drain()] == ["lift"]


def test_virtual_thread_produces_frames(config):
    p = Perception(config.mat, source="virtual")
    vm = VirtualMat(p.feed, frame_hz=200)
    vm.set(3, True)
    vm.start()
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and 3 not in p.snapshot.get().state.occupied:
            time.sleep(0.01)
    finally:
        vm.stop()
    assert p.snapshot.get().state.occupied == {3}
    vm.clear()
    assert vm.stones == frozenset()
