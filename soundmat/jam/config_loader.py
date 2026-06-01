"""加载 jam manifest（TOML）+ 引用的数据文件（YAML）→ 结构化 JamConfig。

manifest 是装配清单，[refs] 指向 data/ 下的具体配置：
  progression → data/progressions/<name>.yaml   （和弦序列 + 每和弦 pad voicing）
  melody_pack → data/melodies/<name>/<chord>.yaml（每和弦 × ring 的 8 八分触发表）
  drums       → data/drums/<name>.yaml           （A/B/C/D pattern + 展开 sequence）
  rings       → data/rings/<name>.yaml           （ring 角色 + 音色 + 增益）
  lofi_mapping→ data/lofi_mapping[/<name>].yaml   （Lo-Fi 强度 → master 参数曲线）

「内容 (What) 与执行 (How) 分离」：换曲子只换这些数据，代码一行不动。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .ring_config import RingConfig
from .scheduler.timing import DEFAULT_SCHEME, Timing

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


@dataclass
class JamConfig:
    # music
    bpm: float = 120.0
    key: str = "C"
    scale: str = "major"
    master_volume: float = 1.0
    scheme: int = DEFAULT_SCHEME
    name: str = "Jam"
    # 结构数据
    progression: list[tuple[str, int]] = field(default_factory=list)
    chord_voicings: dict[str, list[str]] = field(default_factory=dict)
    trigger_tables: dict[str, dict[int, list]] = field(default_factory=dict)
    rings: dict[int, RingConfig] = field(default_factory=dict)
    drum_patterns: dict[str, dict[str, list[int]]] = field(default_factory=dict)
    drum_sequence: list[str] = field(default_factory=list)
    lofi_mapping: dict = field(default_factory=dict)

    @property
    def timing(self) -> Timing:
        return Timing(self.scheme)


def _load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _ring_key_to_int(key: str) -> int:
    return int(str(key).lstrip("Rr"))


def load_jam_config(manifest: dict) -> JamConfig:
    """manifest dict（已含 _dir）→ JamConfig。"""
    base = Path(manifest.get("_dir", "."))
    data_dir = base / "data"
    music = manifest.get("music", {})
    refs = manifest.get("refs", {})

    cfg = JamConfig(
        bpm=float(music.get("bpm", 120)),
        key=str(music.get("key", "C")),
        scale=str(music.get("scale", "major")),
        master_volume=float(music.get("master_volume", 1.0)),
        scheme=int(music.get("scheme", DEFAULT_SCHEME)),
        name=str(manifest.get("name", "Jam")),
    )

    # progression + 和弦 voicing
    prog_name = refs.get("progression")
    if prog_name:
        prog = _load_yaml(data_dir / "progressions" / f"{prog_name}.yaml")
        for entry in prog.get("chords", []):
            cid = entry["id"]
            cfg.progression.append((cid, int(entry.get("bars", 2))))
            if "voicing" in entry:
                cfg.chord_voicings[cid] = list(entry["voicing"])

    # melody pack → trigger_tables[symbol][ring] = [8 tokens]
    pack = refs.get("melody_pack")
    if pack:
        pack_dir = data_dir / "melodies" / str(pack)
        for cid, _bars in cfg.progression:
            ypath = pack_dir / f"{cid}.yaml"
            if not ypath.exists():
                continue
            rows = _load_yaml(ypath)
            cfg.trigger_tables[cid] = {
                _ring_key_to_int(rk): list(rv) for rk, rv in rows.items()
            }

    # rings
    rings_name = refs.get("rings")
    if rings_name:
        rings = _load_yaml(data_dir / "rings" / f"{rings_name}.yaml")
        for rk, rv in rings.items():
            ring = _ring_key_to_int(rk)
            cfg.rings[ring] = RingConfig(
                ring=ring,
                role=rv.get("role", "none"),
                instrument=rv.get("instrument"),
                note_sec=float(rv.get("note_sec", 0.5)),
                tail_sec=float(rv.get("tail_sec", 0.0)),
                gain=float(rv.get("gain", 1.0)),
                params=dict(rv.get("params", {})),
            )

    # drums
    drums_name = refs.get("drums")
    if drums_name:
        drums = _load_yaml(data_dir / "drums" / f"{drums_name}.yaml")
        cfg.drum_patterns = {
            pid: {v: list(pat.get(v, [])) for v in ("kick", "snare", "hihat")}
            for pid, pat in drums.get("patterns", {}).items()
        }
        cfg.drum_sequence = list(drums.get("sequence", []))

    # lofi mapping
    lofi_name = refs.get("lofi_mapping", "default")
    lofi_path = data_dir / "lofi_mapping.yaml"
    if lofi_name and lofi_name != "default":
        cand = data_dir / "lofi_mapping" / f"{lofi_name}.yaml"
        if cand.exists():
            lofi_path = cand
    if lofi_path.exists():
        loaded = _load_yaml(lofi_path)
        cfg.lofi_mapping = loaded.get("master", loaded.get("mapping", loaded))

    return cfg
