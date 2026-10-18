"""编排文件：``arrangements/<标识>/arrangement.toml``（DATA_MODEL「编排」、SONIFICATION「编排的结构」）。

每份编排有共同的头部，头部之外是模式专属的内容，原样交给模式解释：

    id = "kyoto"                  # 可省略，默认是文件夹名
    title = "京都岚山"
    mode = "ambient"
    mode_label = "Ambient · 氛围"
    description = "……"
    ring_labels = ["低音", ...]   # 8 个
    level = -12                   # 可省略：整体电平（dB），默认 0
    [meters]                      # 可省略：控制台的电平条怎样分组，见 sonification/meters.py

编排对声音素材只做引用：引用是素材库 ``samples/`` 下的相对路径。
"""
from __future__ import annotations

import tomllib
from pathlib import Path

from ..config import ROOT
from .mode import Arrangement, LoadError

ARRANGEMENTS_DIR = ROOT / "arrangements"
HEADER = {"id", "title", "mode", "mode_label", "description", "ring_labels", "meters", "level"}


def load_arrangement(folder: Path) -> Arrangement:
    path = folder / "arrangement.toml"
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except FileNotFoundError as e:
        raise LoadError(f"找不到 {path}") from e
    except tomllib.TOMLDecodeError as e:
        raise LoadError(f"{path} 格式错误：{e}") from e
    for key in ("title", "mode"):
        if not isinstance(raw.get(key), str) or not raw[key]:
            raise LoadError(f"{path} 缺少 {key}")
    labels = raw.get("ring_labels", [])
    if labels and len(labels) != 8:
        raise LoadError(f"{path} 的 ring_labels 应有 8 项")
    meters = raw.get("meters", {})
    if not isinstance(meters, dict):
        raise LoadError(f"{path} 的 meters 应是一个表")
    level = raw.get("level", 0.0)
    if isinstance(level, bool) or not isinstance(level, (int, float)) or not -60 <= level <= 12:
        raise LoadError(f"{path} 的 level 应是 -60 到 12 之间的分贝数")
    content = {k: v for k, v in raw.items() if k not in HEADER}
    return Arrangement(
        id=raw.get("id") or folder.name,
        title=raw["title"],
        mode=raw["mode"],
        description=raw.get("description", ""),
        mode_label=raw.get("mode_label", raw["mode"]),
        ring_labels=tuple(labels),
        meters=meters,
        level=float(level),
        content=content,
        path=str(folder),
    )


def discover(root: Path = ARRANGEMENTS_DIR) -> tuple[dict[str, Arrangement], list[str]]:
    """读取全部编排。返回 (标识 → 编排, 错误信息列表)；一份编排出错不影响其他编排。"""
    found: dict[str, Arrangement] = {}
    errors: list[str] = []
    if not root.is_dir():
        return found, [f"编排目录不存在：{root}"]
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        if not (folder / "arrangement.toml").exists():
            continue
        try:
            a = load_arrangement(folder)
        except LoadError as e:
            errors.append(str(e))
            continue
        if a.id in found:
            errors.append(f"编排标识重复：{a.id}")
            continue
        found[a.id] = a
    return found, errors
