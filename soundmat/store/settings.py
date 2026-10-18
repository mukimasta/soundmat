"""设置：随场地和使用而变化的参数，由状态中心持久保存（DATA_MODEL「配置与设置」）。

设置放在状态树的 ``settings`` 下，保存为 ``<数据目录>/settings.json``。写入时先写临时文件
再整体替换，避免断电损坏（TECH_STACK「存储」）。每项修改都经过校验，非法值不会进入状态中心。
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable

from ..config import ROOT
from ..errors import InvalidRequest
from ..sound.spatial import PRESETS, SpeakerLayout
from . import Store

log = logging.getLogger("soundmat.settings")


def default_sound_library() -> str:
    """声音素材库的默认位置：树莓派上与程序目录并列的 ``sound/``，开发机上是 SoundMat 总文件夹的 ``sound/``。"""
    env = os.environ.get("SOUNDMAT_SOUND")
    if env:
        return env
    for cand in (ROOT.parent / "sound", ROOT.parent.parent.parent / "sound"):
        if (cand / "samples").is_dir():
            return str(cand)
    return str(ROOT.parent / "sound")


def defaults(data_dir: Path) -> dict:
    return {
        "sound": {
            "layout": PRESETS["stereo"].to_json(),
            "orientation": 0.0,
            "volume": 0.8,
        },
        "run": {
            "defaultArrangement": "kyoto",
            "soundLibrary": default_sound_library(),
        },
        "recording": {
            "path": str(data_dir / "recordings"),
            "stems": True,
        },
    }


def _number(lo: float, hi: float) -> Callable[[Any], float]:
    def check(v: Any) -> float:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError("应为数值")
        if not lo <= v <= hi:
            raise ValueError(f"应在 {lo} 到 {hi} 之间")
        return float(v)
    return check


def _orientation(v: Any) -> float:
    return _number(-360, 360)(v) % 360


def _layout(v: Any) -> dict:
    if isinstance(v, str):
        if v not in PRESETS:
            raise ValueError(f"未知的音箱布局 {v}")
        return PRESETS[v].to_json()
    if not isinstance(v, dict):
        raise ValueError("应为布局名称或 {azimuths, names}")
    lay = SpeakerLayout.from_json(v)
    if lay.channels > 8:
        raise ValueError("最多支持 8 只音箱")
    return lay.to_json()


def _text(v: Any) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ValueError("应为非空文字")
    return v.strip()


def _abs_path(v: Any) -> str:
    """目录位置必须是绝对路径：相对路径会按主机程序的工作目录算，装置上那是当前版本的目录，
    更新几次之后旧版本目录被清理，里面的东西（例如录音）就跟着没了。"""
    text = _text(v)
    if not Path(text).expanduser().is_absolute():
        raise ValueError("应为绝对路径，例如 /home/soundmat/data/recordings")
    return str(Path(text).expanduser())


def _bool(v: Any) -> bool:
    if not isinstance(v, bool):
        raise ValueError("应为是或否")
    return v


VALIDATORS: dict[str, Callable[[Any], Any]] = {
    "sound.layout": _layout,
    "sound.orientation": _orientation,
    "sound.volume": _number(0, 1),
    "run.defaultArrangement": _text,
    "run.soundLibrary": _abs_path,
    "recording.path": _abs_path,
    "recording.stems": _bool,
}


class Settings:
    def __init__(self, store: Store, data_dir: Path):
        self.store = store.writer("settings")
        self.path = Path(data_dir) / "settings.json"
        self._lock = threading.Lock()
        data = defaults(Path(data_dir))
        # 只保存改过的项：默认值（声音素材库、录音位置）每次启动时重新得出，
        # 所以移动程序目录或设置 SOUNDMAT_SOUND 后仍然生效。
        self._changed: dict[str, Any] = {}
        for key, value in self._read().items():
            if key in VALIDATORS:
                try:
                    self._changed[key] = VALIDATORS[key](value)
                    _set(data, key, self._changed[key])
                except ValueError as e:
                    log.warning("设置 %s 的值无效（%s），使用默认值", key, e)
        self.store.set("settings", data)

    def _read(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text("utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            log.warning("无法读取设置文件 %s（%s），使用默认设置", self.path, e)
            return {}
        flat: dict[str, Any] = {}
        _flatten(raw, "", flat)
        return flat

    def get(self, key: str, default: Any = None) -> Any:
        return self.store.get(f"settings.{key}", default)

    def snapshot(self) -> dict:
        """全部设置（例如写进录制信息）。"""
        return self.store.get("settings", {})

    def update(self, changes: dict[str, Any]) -> dict[str, Any]:
        """校验并应用修改，立即保存。任何一项非法时抛出 ``InvalidRequest``，什么都不改。"""
        clean = {}
        for key, value in changes.items():
            check = VALIDATORS.get(key)
            if check is None:
                raise InvalidRequest(f"未知的设置项：{key}")
            try:
                clean[key] = check(value)
            except ValueError as e:
                raise InvalidRequest(f"{key}：{e}") from e
        with self._lock:
            self.store.update({f"settings.{k}": v for k, v in clean.items()})
            self._changed.update(clean)
            self._save()
        return clean

    def _save(self) -> None:
        data: dict = {}
        for key, value in self._changed.items():
            _set(data, key, value)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".settings-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


def _set(tree: dict, path: str, value: Any) -> None:
    keys = path.split(".")
    for k in keys[:-1]:
        tree = tree.setdefault(k, {})
    tree[keys[-1]] = value


def _flatten(node: Any, prefix: str, out: dict) -> None:
    if isinstance(node, dict) and f"{prefix}".rstrip(".") not in VALIDATORS:
        for k, v in node.items():
            _flatten(v, f"{prefix}{k}.", out)
    else:
        out[prefix.rstrip(".")] = node
