"""把控制台录下的压力图重新喂给感知，统计放下、拿起、挪动，和按区判断的旧做法对比。

    uv run python scripts/replay_mat.py <录制文件夹> [...] [--events] [--legacy]

录制里的压力图约 10 帧/秒（控制器约 29 帧/秒），时间相关的判断按秒计算，精度比实机粗。
2026-10-20 01:19 之前的录制是内两环改正之前的坐标（DECISION 第 13 条），自动换算到现在的坐标。

对比的旧做法：

- ``v1``：第一版的阈值（单区 500，放下 40 ms、拿起 80 ms），每个区各自判断，2026-10-18 演出时就是这样；
- ``zones``：4d2b1a0 的按区判断（外环 245、内两环 185，拿起低于其 0.67 倍，放下、拿起各 80 ms）。

统计里"闪"指一颗石头不到 0.5 秒就被拿起；"拿起又放下"指拿起后 1 秒内在同一个区或相邻的区又放下，
多半是读数掉下去又回来，或者拖动被拆成了拿起加放下。
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from soundmat.config import load_config  # noqa: E402
from soundmat.perception import tracker_params  # noqa: E402
from soundmat.perception.interpret import Interpreter  # noqa: E402
from soundmat.perception.interpret.stones import NEIGHBOURS  # noqa: E402
from soundmat.perception.model import PressureMap  # noqa: E402
from soundmat.perception.signal import zone_wire_index  # noqa: E402
from soundmat.perception.zones import INNER_RINGS, NUM_ZONES, ZONES  # noqa: E402

INNER_FIX = datetime.fromisoformat("2026-10-20T01:19:00-07:00")


def _v1_zone_wires() -> np.ndarray:
    """第一版（内两环镜像两次）的"区域 → 接线读数"索引表。"""
    ids = np.arange(256).reshape(8, 32)[:, ::-1]
    logical = np.full((8, 32), -1)
    for ring in range(8):
        pre = np.full(32, -1)
        if ring < INNER_RINGS:
            for k in range(16):
                pre[2 * k + 1] = ids[ring, 2 * (15 - k) + 1]
        else:
            pre[:] = ids[ring]
        logical[ring] = [pre[(s - 4) % 32] for s in range(32)]
    return np.array([logical[z.ring, 2 * z.slot + 1 if z.ring < INNER_RINGS else z.slot] for z in ZONES])


def load(folder: Path, v1_layout: bool | None = None) -> tuple[np.ndarray, np.ndarray, dict]:
    info = json.loads((folder / "info.json").read_text())
    if v1_layout is None:
        v1_layout = datetime.fromisoformat(info["startedAt"]) < INNER_FIX
    times, frames = [], []
    with open(folder / "session.jsonl") as f:
        for line in f:
            if '"pressure"' not in line:
                continue
            m = json.loads(line)
            if m.get("type") == "pressure":
                times.append(m["t"])
                frames.append(m["values"])
    t = np.array(times)
    v = np.array(frames, dtype=np.float32) / 1000
    if v1_layout:
        new = zone_wire_index(True, 4)
        old = _v1_zone_wires()
        v = v[:, [int(np.flatnonzero(old == w)[0]) for w in new]]
    return t - t[0], v, info


@dataclass
class Ev:
    t: float
    kind: str
    zone: int | None
    stone: int | None = None
    src: int | None = None


def run_tracker(t: np.ndarray, v: np.ndarray, cfg) -> tuple[list[Ev], np.ndarray]:
    it = Interpreter(tracker_params(cfg), settle=cfg.settle)
    out, count = [], np.zeros(len(t), dtype=int)
    for i in range(len(t)):
        state, ev, _ = it.update(PressureMap(t=float(t[i]), seq=i, values=v[i]))
        out += [Ev(e.t, e.kind, e.zone, e.stone, e.from_zone) for e in ev]
        count[i] = len(state.stones)
    return out, count


def run_zones(t: np.ndarray, v: np.ndarray, place: np.ndarray, release: np.ndarray,
              occupy_hold: float, release_hold: float) -> tuple[list[Ev], np.ndarray]:
    """按区判断（旧做法）：每个区各自过阈值、各自去抖。"""
    occ = np.zeros(NUM_ZONES, bool)
    since = np.full(NUM_ZONES, np.nan)
    out, count = [], np.zeros(len(t), dtype=int)
    for i in range(len(t)):
        raw = np.where(occ, v[i] >= release, v[i] >= place)
        diff = raw != occ
        since[diff & np.isnan(since)] = t[i]
        since[~diff] = np.nan
        commit = diff & (t[i] - since >= np.where(occ, release_hold, occupy_hold) - 1e-9)
        for z in np.flatnonzero(commit):
            out.append(Ev(float(t[i]), "lift" if occ[z] else "place", int(z)))
        occ[commit] = ~occ[commit]
        since[commit] = np.nan
        count[i] = int(occ.sum())
    return out, count


def legacy(t, v, which: str):
    inner = np.array([z.ring < INNER_RINGS for z in ZONES])
    if which == "v1":
        th = np.full(NUM_ZONES, 500 / 4095)
        return run_zones(t, v, th, th, 0.04, 0.08)
    th = np.where(inner, 185 / 4095, 245 / 4095)
    return run_zones(t, v, th, th * 0.67, 0.08, 0.08)


def summarize(events: list[Ev], count: np.ndarray, t: np.ndarray) -> dict:
    places = [e for e in events if e.kind == "place"]
    lifts = [e for e in events if e.kind == "lift"]
    moves = [e for e in events if e.kind == "move"]
    # 每颗石头（或每个区的每次占用）活了多久
    born: dict = {}
    life = []
    for e in events:
        key = e.stone if e.stone is not None else ("z", e.zone)
        if e.kind == "place":
            born[key] = e.t
        elif e.kind == "lift" and key in born:
            life.append(e.t - born.pop(key))
    life = np.array(life) if life else np.zeros(0)
    # 拿起后 1 秒内在同一个区或相邻的区又放下
    replaced = 0
    for lf in lifts:
        near = {lf.zone, *NEIGHBOURS[lf.zone]}
        if any(0 <= p.t - lf.t <= 1.0 and p.zone in near for p in places):
            replaced += 1
    dt = np.diff(t, append=t[-1])
    return {
        "放下": len(places), "拿起": len(lifts), "挪动": len(moves),
        "闪（<0.5 s）": int((life < 0.5).sum()),
        "拿起又放下（1 s 内、同区或相邻）": replaced,
        "平均石头数": round(float((count * dt).sum() / max(dt.sum(), 1e-9)), 1),
        "最多": int(count.max()) if len(count) else 0,
        "寿命中位数（s）": round(float(np.median(life)), 1) if len(life) else None,
        "静下来": sum(e.kind == "settle" for e in events),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folders", nargs="+", type=Path)
    ap.add_argument("--events", action="store_true", help="列出新做法的每个事件")
    ap.add_argument("--legacy", action="store_true", help="同时统计两种按区判断的旧做法")
    ap.add_argument("--config", type=Path, default=None)
    args = ap.parse_args()
    cfg = load_config(args.config).mat
    for folder in args.folders:
        t, v, info = load(folder)
        print(f"\n## {folder.name}（{info['arrangement']['title']}，{t[-1]:.0f} 秒，{len(t)} 帧）")
        rows = {"石头": summarize(*run_tracker(t, v, cfg), t)}
        if args.legacy:
            rows["zones"] = summarize(*legacy(t, v, "zones"), t)
            rows["v1"] = summarize(*legacy(t, v, "v1"), t)
        keys = list(next(iter(rows.values())))
        print("| | " + " | ".join(rows) + " |")
        print("|---|" + "---|" * len(rows))
        for k in keys:
            print(f"| {k} | " + " | ".join(str(r[k]) for r in rows.values()) + " |")
        if args.events:
            evs, _ = run_tracker(t, v, cfg)
            for e in evs:
                z = ZONES[e.zone].id if e.zone is not None else ""
                src = f" ← {ZONES[e.src].id}" if e.src is not None else ""
                print(f"  {e.t:7.2f}s  {e.kind:6s} 石头{e.stone or '':<4} {z}{src}")


if __name__ == "__main__":
    main()
