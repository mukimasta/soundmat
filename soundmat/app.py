"""ModeManager + manifest 加载。

主程序根据 manifest 的 `mode` 字段选启动哪个模式 app。运行时只有一个模式 active；
切换通过 Web 控制台触发，scsynth 常驻不重启——切换只是在它内部起停 synth 节点。

模式切换（设计文档 §8）：取锁 → 旧 app.stop()（free 自己的 SC group）→ 加载新 manifest
→ 选 AmbientApp/JamApp → 构造 → new_app.start()（new_group + 订阅 + 主循环）。
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any

from . import config
from .core.services import SharedServices

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


def load_manifest(path: str | Path) -> dict:
    """读 manifest TOML → dict。附带绝对路径与所在目录，供模式 config_loader 解析引用。"""
    path = Path(path).resolve()
    with open(path, "rb") as f:
        data = tomllib.load(f)
    data.setdefault("_path", str(path))
    data.setdefault("_dir", str(path.parent))
    return data


def manifest_path_key(path: str | Path) -> str:
    """Canonical manifest path for API + Web UI matching."""
    return str(Path(path).resolve())


def manifest_rel_key(path: str | Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(Path(path).resolve().relative_to(config.MANIFEST_DIR))
    except ValueError:
        return None


class ModeManager:
    """持有 SharedServices，管理当前 active 模式 app 的生命周期与切换。"""

    def __init__(self, services: SharedServices):
        self.services = services
        self.current_app = None
        self.current_manifest: dict | None = None
        self.current_path: str | None = None
        self._lock = threading.RLock()

    # ── 模式注册（懒导入，避免循环依赖；ambient 可为 shell）──
    def _mode_class(self, mode: str):
        if mode == "jam":
            from .jam.app import JamApp
            return JamApp
        if mode == "ambient":
            from .ambient.app import AmbientApp
            return AmbientApp
        raise ValueError(f"未知模式: {mode!r}")

    def switch_to(self, manifest_path: str | Path) -> dict:
        with self._lock:
            manifest = load_manifest(manifest_path)
            mode = manifest.get("mode")
            cls = self._mode_class(mode)

            if self.current_app is not None:
                self.current_app.stop()
                self.current_app = None

            app = cls(manifest, self.services)
            app.start()
            self.current_app = app
            self.current_manifest = manifest
            self.current_path = manifest_path_key(manifest_path)
            return self.status()

    def stop_current(self) -> None:
        with self._lock:
            if self.current_app is not None:
                self.current_app.stop()

    def start_current(self) -> None:
        with self._lock:
            if self.current_app is not None:
                self.current_app.start()

    def set_param(self, key: str, value: Any) -> None:
        with self._lock:
            if self.current_app is not None:
                self.current_app.set_param(key, value)

    def status(self) -> dict:
        with self._lock:
            base = {
                "manifest": self.current_path,
                "manifest_rel": manifest_rel_key(self.current_path),
                "mode": (self.current_manifest or {}).get("mode"),
                "name": (self.current_manifest or {}).get("name"),
            }
            if self.current_app is not None:
                base["app"] = self.current_app.status()
            return base

    def shutdown(self) -> None:
        self.stop_current()


def list_manifests() -> list[dict]:
    """扫描 manifest/ 下所有 .toml，返回 [{path, mode, name}]，供 Web 控制台列表。"""
    out = []
    for path in sorted(config.MANIFEST_DIR.rglob("*.toml")):
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except Exception:
            continue
        if "mode" not in data:
            continue
        rel = path.relative_to(config.MANIFEST_DIR)
        out.append({
            "path": manifest_path_key(path),
            "rel": str(rel),
            "mode": data.get("mode"),
            "name": data.get("name", str(rel)),
            "description": data.get("description", ""),
        })
    return out
