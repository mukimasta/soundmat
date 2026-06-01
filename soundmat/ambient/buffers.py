"""样本清单 → scsynth buffer。

读 manifest 的 [samples.*]，把每个 wav 通过 SCServerHandle 加载成 buffer，
维护 sample_id → Buffer 表；按声道数决定用哪个 player synthdef。
"""
from __future__ import annotations

from .. import config


class BufferPool:
    def __init__(self, sc):
        self._sc = sc            # SCServerHandle
        self._by_id: dict = {}   # sample_id -> Buffer

    def load_manifest(self, manifest: dict) -> None:
        for sid, cfg in manifest.get("samples", {}).items():
            path = config.SAMPLES_DIR / "kyoto" / cfg["file"]
            self._by_id[sid] = self._sc.read_buffer(path)

    def get(self, sample_id: str):
        return self._by_id[sample_id]

    def synthdef_for(self, sample_id: str, tune: bool = False) -> str:
        """按声道数选 def：1ch → playMono，2ch → playStereo；tune=True 选变调变体。"""
        mono = self._by_id[sample_id].num_channels == 1
        base = "playMono" if mono else "playStereo"
        return base + "Tune" if tune else base
