import threading

from soundmat.exchange import EventHub, EventQueue, Latest


def test_latest_overwrites_and_versions():
    l = Latest(1)
    assert l.get_versioned() == (1, 0)
    l.set(2)
    l.set(3)
    assert l.get_versioned() == (3, 2)


def test_event_queue_drains_everything_once():
    q = EventQueue()
    q.put(1)
    q.put_many([2, 3])
    assert q.drain() == [1, 2, 3]
    assert q.drain() == []


def test_hub_fans_out_to_each_subscriber():
    hub = EventHub()
    a, b = hub.subscribe(), hub.subscribe()
    hub.publish([1, 2])
    assert a.drain() == [1, 2]
    hub.publish([3])
    assert a.drain() == [3]
    assert b.drain() == [1, 2, 3]


def test_no_events_lost_under_concurrency():
    q = EventQueue()
    got = []

    def producer():
        for i in range(5000):
            q.put(i)

    th = threading.Thread(target=producer)
    th.start()
    while th.is_alive() or len(q):
        got.extend(q.drain())
    th.join()
    got.extend(q.drain())
    assert got == list(range(5000))
