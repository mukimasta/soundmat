import pytest

from soundmat.sonification.arrangements import ARRANGEMENTS_DIR, discover, load_arrangement
from soundmat.sonification.mode import LoadError


def test_repo_arrangements_load():
    found, errors = discover(ARRANGEMENTS_DIR)
    assert errors == []
    k = found["kyoto"]
    assert k.title == "京都岚山" and k.mode == "ambient"
    assert len(k.ring_labels) == 8
    assert "rings" in k.content and "title" not in k.content


def test_errors_are_isolated(tmp_path):
    (tmp_path / "good").mkdir()
    (tmp_path / "good" / "arrangement.toml").write_text('title = "G"\nmode = "x"\n')
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "arrangement.toml").write_text('title = "B"\n')
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "arrangement.toml").write_text('title = \n')
    (tmp_path / "labels").mkdir()
    (tmp_path / "labels" / "arrangement.toml").write_text('title = "L"\nmode = "x"\nring_labels = ["a"]\n')
    found, errors = discover(tmp_path)
    assert list(found) == ["good"]
    assert len(errors) == 3
    with pytest.raises(LoadError):
        load_arrangement(tmp_path / "missing")


def test_level_header(tmp_path):
    import pytest

    from soundmat.sonification.arrangements import ARRANGEMENTS_DIR, load_arrangement
    from soundmat.sonification.mode import LoadError

    assert load_arrangement(ARRANGEMENTS_DIR / "lofi_1").level == -12
    assert load_arrangement(ARRANGEMENTS_DIR / "kyoto").level == 0
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "arrangement.toml").write_text('title = "X"\nmode = "jam"\nlevel = "loud"\n')
    with pytest.raises(LoadError, match="level"):
        load_arrangement(tmp_path / "x")


def test_repo_arrangements_use_defined_instruments():
    """每份编排用到的音色（和共用效果）都在 instruments/ 的源码里定义过：名字拼错时这里就能发现，
    不用等到装置上没声音。"""
    import re

    from soundmat.config import ROOT
    from soundmat.sonification.mode import ModeContext
    from soundmat.supervisor import MODES

    source = "\n".join(p.read_text() for p in (ROOT / "instruments").rglob("*.scd"))
    defined = set(re.findall(r'~smDef\.\("(\w+)"', source)) | set(re.findall(r"\\(\w+)", source))
    found, _ = discover(ARRANGEMENTS_DIR)
    for arr in found.values():
        mode = MODES[arr.mode](arr, ModeContext(led_count=108))
        plan = mode.load()
        missing = (set(plan.instruments) | {plan.fx}) - defined
        assert not missing, f"{arr.id} 用到未定义的音色：{sorted(missing)}"
