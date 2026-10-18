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
