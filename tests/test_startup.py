"""启动：按需启动合成器服务、打印控制台网址。"""
import socket

from soundmat.__main__ import console_urls
from soundmat.sound import scsynth_process as sp


def test_console_urls():
    urls = console_urls("0.0.0.0", 8000, "soundmat-pi", "192.168.0.49")
    assert urls == [("本机", "http://localhost:8000"), ("局域网", "http://soundmat-pi.local:8000"),
                    ("局域网", "http://192.168.0.49:8000")]
    assert console_urls("0.0.0.0", 8000, "Mac.local", None)[1] == ("局域网", "http://Mac.local:8000")
    assert console_urls("127.0.0.1", 9000, "x", "10.0.0.2") == [("本机", "http://localhost:9000")]


def _free_udp_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_connects_to_running_synth_without_starting(monkeypatch):
    monkeypatch.setattr(sp, "responding", lambda host, port: True)
    monkeypatch.setattr(sp.ScsynthProcess, "start", lambda self, timeout=10.0: (_ for _ in ()).throw(AssertionError))
    assert sp.ensure_scsynth("127.0.0.1", 57110, 2, 48000) is None


def test_never_starts_under_systemd_or_for_remote_host(monkeypatch):
    monkeypatch.setattr(sp, "responding", lambda host, port: False)
    monkeypatch.setattr(sp.ScsynthProcess, "start", lambda self, timeout=10.0: (_ for _ in ()).throw(AssertionError))
    monkeypatch.setenv("INVOCATION_ID", "abc")
    assert sp.ensure_scsynth("127.0.0.1", 57110, 2, 48000) is None
    monkeypatch.delenv("INVOCATION_ID")
    assert sp.ensure_scsynth("192.168.0.9", 57110, 2, 48000) is None


def test_starts_own_scsynth_and_stops_it(monkeypatch, tmp_path):
    """用一个假的 scsynth（打印 server ready 后一直等着）：没有合成器服务时启动它，stop 时结束它。"""
    fake = tmp_path / "scsynth"
    fake.write_text("#!/bin/sh\necho \"$@\" > \"$(dirname \"$0\")/args\"\necho 'SuperCollider 3 server ready.'\nexec sleep 30\n")
    fake.chmod(0o755)
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    monkeypatch.setenv("SOUNDMAT_SCSYNTH", str(fake))
    port = _free_udp_port()
    proc = sp.ensure_scsynth("127.0.0.1", port, 4, 48000)
    assert proc is not None and proc.proc.poll() is None
    assert (tmp_path / "args").read_text().split() == ["-u", str(port), "-i", "0", "-o", "4", "-S", "48000"]
    proc.stop()
    assert proc.proc.poll() is not None


def test_thread_names_reach_the_os():
    import sys
    import threading

    from soundmat import threadnames

    threadnames.install()
    seen = {}

    def work():
        if sys.platform.startswith("linux"):
            seen["comm"] = open(f"/proc/self/task/{threading.get_native_id()}/comm").read().strip()
        else:
            seen["comm"] = "sonification"
    t = threading.Thread(target=work, name="sonification")
    t.start(); t.join()
    assert seen["comm"] == "sonification"
