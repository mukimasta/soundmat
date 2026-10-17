import numpy as np
import pytest
import soundfile

from soundmat.sonification.mode import LoadError
from soundmat.sound.assets import AssetLibrary
from soundmat.sound.backend import RecordingBackend


def wav(root, ref, seconds=1.0, channels=2, sr=48000):
    p = root / "samples" / ref
    p.parent.mkdir(parents=True, exist_ok=True)
    soundfile.write(str(p), np.zeros((int(seconds * sr), channels), dtype=np.float32), sr, subtype="PCM_24")
    return p


def test_budget_refcount_and_missing(tmp_path):
    wav(tmp_path, "a.wav")                    # 48000 × 2 × 4 = 384000 字节
    wav(tmp_path, "b.wav", channels=1)        # 192000 字节
    be = RecordingBackend()
    lib = AssetLibrary(tmp_path, budget_mb=0.6, backend=be)
    assert lib.info("a.wav").bytes == 384000
    missing = lib.acquire("A", {"a.wav", "gone.wav"}, at=0)
    assert missing == ["gone.wav"]
    assert [c.args["ref"] for c in be.of_kind("load_asset")] == ["a.wav"]
    # 共用的素材只加载一份
    lib.acquire("B", {"a.wav", "b.wav"}, at=1)
    assert [c.args["ref"] for c in be.of_kind("load_asset")] == ["a.wav", "b.wav"]
    lib.release("A", at=2)
    assert be.of_kind("free_asset") == []
    lib.release("B", at=3)
    assert sorted(c.args["ref"] for c in be.of_kind("free_asset")) == ["a.wav", "b.wav"]
    assert lib.loaded == {}


def test_over_budget_loads_nothing(tmp_path):
    wav(tmp_path, "a.wav")
    wav(tmp_path, "big.wav", seconds=3)
    be = RecordingBackend()
    lib = AssetLibrary(tmp_path, budget_mb=1.0, backend=be)
    with pytest.raises(LoadError, match="超过内存预算"):
        lib.acquire("A", {"a.wav", "big.wav"}, at=0)
    assert lib.loaded == {} and be.of_kind("load_asset") == []


def test_no_library_at_all(tmp_path):
    lib = AssetLibrary(tmp_path / "nowhere", 10, RecordingBackend())
    assert lib.acquire("A", {"x.wav"}, 0) == ["x.wav"]
