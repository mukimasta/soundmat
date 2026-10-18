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


def test_directory_settings_must_be_absolute(tmp_path):
    """录音位置和素材库位置必须是绝对路径：相对路径会落进装置上当前版本的目录，更新后被清掉。"""
    import json

    import pytest

    from soundmat.errors import InvalidRequest

    s = Settings(Store(), tmp_path)
    assert s.get("recording.path") == str(tmp_path / "recordings")
    with pytest.raises(InvalidRequest, match="绝对路径"):
        s.update({"recording.path": "data/recordings"})
    with pytest.raises(InvalidRequest, match="绝对路径"):
        s.update({"run.soundLibrary": "sound"})
    s.update({"recording.path": str(tmp_path / "rec")})
    # 设置文件里已有的相对路径：读取时当作无效，回到默认值
    (tmp_path / "settings.json").write_text(json.dumps({"recording": {"path": "data/recordings"}}))
    assert Settings(Store(), tmp_path).get("recording.path") == str(tmp_path / "recordings")
