"""状态树的每一段都登记过、只有一个写入者；控制台读的路径都在登记过的段里（store/branches.py）。"""
import re
from pathlib import Path

from soundmat.clock import Beat
from soundmat.store.branches import BRANCHES, branch_of

CONSOLE_SRC = Path(__file__).resolve().parent.parent / "console" / "src"


def test_running_program_writes_only_registered_branches(make_sup, tmp_path, monkeypatch):
    monkeypatch.setenv("SOUNDMAT_SOUND", str(tmp_path / "no-sound"))
    sup = make_sup()
    sup.catalog.play("kyoto")
    sup.sonification.on_beat(Beat(0, 1.0, 1 / 60))
    sup.monitor.step()
    snap = sup.store.snapshot()
    written = {f"{top}.{key}" for top in ("status", "catalog") for key in snap.get(top, {})} | {"settings"}
    assert all(branch_of(p) == p for p in written), sorted(p for p in written if branch_of(p) != p)
    assert set(sup.store._owned) == set(BRANCHES)          # 每一段都有、且只有一个写入者


def console_paths() -> set[str]:
    paths = set()
    for f in CONSOLE_SRC.rglob("*.ts*"):
        paths |= set(re.findall(r"['\"`]((?:status|catalog|settings)\.[A-Za-z.]+)['\"`]", f.read_text("utf-8")))
    return paths


def test_console_reads_paths_the_program_writes(make_sup, tmp_path, monkeypatch):
    """控制台读的每个路径，运行中的主机程序都真的写了（改了路径而控制台没跟上时在这里发现）。"""
    monkeypatch.setenv("SOUNDMAT_SOUND", str(tmp_path / "no-sound"))
    sup = make_sup()
    sup.catalog.play("kyoto")
    sup.sonification.on_beat(Beat(0, 1.0, 1 / 60))
    sup.monitor.step()
    missing = object()
    paths = console_paths()
    assert paths, "没有找到控制台读取的路径"
    assert not [p for p in paths if branch_of(p) is None]
    assert sorted(p for p in paths if sup.store.get(p, missing) is missing) == []
