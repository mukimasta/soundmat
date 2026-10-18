"""素材库：按编排加载和卸载声音素材，加载前检查内存预算（SOUND_ENGINE「素材库」）。

素材以素材库 ``samples/`` 下的相对路径标识。加载一份编排时先算出它引用的、还没加载的素材
需要多少内存（合成器服务把素材解码成 32 位浮点放在内存里：帧数 × 声道数 × 4 字节），
放得下才加载，放不下就整份拒绝，不会只加载一部分。素材按引用计数管理：切换编排时新旧
两份编排共用的素材只加载一份；某份编排停止后，只被它使用的素材被释放。

缺失的素材不阻止编排加载：它们被报告给系统监测，用到它们的声音不会发声。
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import soundfile

from ..sonification.mode import LoadError
from .backend import Backend

log = logging.getLogger("soundmat.sound")


@dataclass(frozen=True)
class AssetInfo:
    ref: str
    path: Path
    channels: int
    frames: int
    sample_rate: int

    @property
    def bytes(self) -> int:
        return self.frames * self.channels * 4


class AssetLibrary:
    def __init__(self, root: Path, budget_mb: float, backend: Backend):
        self.root = Path(root)
        self.budget = int(budget_mb * 1024 * 1024)
        self.backend = backend
        self._lock = threading.Lock()
        self._info: dict[str, AssetInfo | None] = {}
        self.loaded: dict[str, AssetInfo] = {}
        self.owners: dict[str, set[str]] = {}

    @property
    def samples_dir(self) -> Path:
        return self.root / "samples"

    def set_root(self, root: Path) -> None:
        with self._lock:
            self.root = Path(root)
            self._info.clear()

    def info(self, ref: str) -> AssetInfo | None:
        """读取素材文件头；文件不存在或无法读取时返回 None。结果缓存。"""
        with self._lock:
            if ref in self._info:
                return self._info[ref]
        path = self.samples_dir / ref
        try:
            i = soundfile.info(str(path))
            info = AssetInfo(ref, path, i.channels, i.frames, i.samplerate)
        except Exception:  # 文件不存在、格式不支持或损坏
            info = None
        with self._lock:
            self._info[ref] = info
        return info

    def missing(self, refs) -> list[str]:
        return sorted(r for r in refs if self.info(r) is None)

    @property
    def used_bytes(self) -> int:
        return sum(i.bytes for i in self.loaded.values())

    def acquire(self, owner: str, refs, at: float) -> list[str]:
        """为 ``owner`` 加载素材；返回缺失的素材。超出预算时抛出 ``LoadError``，什么都不加载。"""
        refs = set(refs)
        missing = self.missing(refs)
        new = [self.info(r) for r in sorted(refs) if r not in self.loaded and r not in missing]
        need = sum(i.bytes for i in new)
        if self.used_bytes + need > self.budget:
            raise LoadError(
                f"声音素材需要 {_mb(self.used_bytes + need)}，超过内存预算 {_mb(self.budget)}")
        for info in new:
            self.loaded[info.ref] = info
            self.backend.load_asset(info.ref, at)
        for r in refs - set(missing):
            self.owners.setdefault(r, set()).add(owner)
        return missing

    def release(self, owner: str, at: float) -> None:
        for ref in list(self.owners):
            users = self.owners[ref]
            users.discard(owner)
            if not users:
                del self.owners[ref]
                if self.loaded.pop(ref, None) is not None:
                    self.backend.free_asset(ref, at)

    def reload_all(self, at: float) -> None:
        """合成器服务重启后重新加载全部已加载的素材。"""
        for ref in self.loaded:
            self.backend.load_asset(ref, at)

    def path_of(self, ref: str) -> Path:
        return self.samples_dir / ref

    def status(self) -> dict:
        return {
            "loaded": len(self.loaded),
            "memoryMB": round(self.used_bytes / 1024 / 1024, 1),
            "budgetMB": round(self.budget / 1024 / 1024, 1),
            "library": str(self.root),
        }


def _mb(b: int) -> str:
    return f"{b / 1024 / 1024:.0f} MB"
