import json

import pytest

from soundmat.store import Store
from soundmat.store.settings import Settings


def test_defaults_update_and_persist(tmp_path):
    s = Settings(Store(), tmp_path)
    assert s.get("sound.volume") == 0.8
    assert s.get("sound.layout")["azimuths"] == [330.0, 30.0]
    s.update({"sound.volume": 0.5, "sound.layout": "quad", "sound.orientation": -15})
    saved = json.loads((tmp_path / "settings.json").read_text())
    assert saved["sound"]["volume"] == 0.5
    assert saved["sound"]["orientation"] == 345.0
    assert "run" not in saved and "recording" not in saved            # 没改过的项不写入
    s2 = Settings(Store(), tmp_path)
    assert s2.get("sound.layout")["names"] == ["左前", "右前", "右后", "左后"]
    assert list(tmp_path.iterdir()) == [tmp_path / "settings.json"]   # 没有残留的临时文件


@pytest.mark.parametrize("changes", [
    {"sound.volume": 2}, {"sound.volume": "x"}, {"sound.layout": "hexa"},
    {"recording.stems": "yes"}, {"nope": 1}, {"run.defaultArrangement": " "},
])
def test_invalid_changes_rejected_atomically(tmp_path, changes):
    s = Settings(Store(), tmp_path)
    with pytest.raises(ValueError):
        s.update({"sound.orientation": 30, **changes})
    assert s.get("sound.orientation") == 0.0


def test_corrupt_or_invalid_file_falls_back(tmp_path):
    (tmp_path / "settings.json").write_text("{not json")
    assert Settings(Store(), tmp_path).get("sound.volume") == 0.8
    (tmp_path / "settings.json").write_text(json.dumps({"sound": {"volume": 9, "orientation": 90}}))
    s = Settings(Store(), tmp_path)
    assert s.get("sound.volume") == 0.8 and s.get("sound.orientation") == 90.0


def test_unchanged_defaults_follow_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("SOUNDMAT_SOUND", "/first")
    Settings(Store(), tmp_path).update({"sound.volume": 0.5})
    monkeypatch.setenv("SOUNDMAT_SOUND", "/second")
    s = Settings(Store(), tmp_path)
    assert s.get("run.soundLibrary") == "/second" and s.get("sound.volume") == 0.5
