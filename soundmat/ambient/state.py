"""State：垫面快照（绝对）+ 本帧增量（边沿事件）。

State（occupied + 每环石头数）喂 mapper 持续层；events（Place/Remove）只喂触发层。
（从 sonification/soundmat/state.py 迁移，几何按 config 的非均匀环数。）
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import config


@dataclass
class State:
    occupied: set[tuple[int, int]] = field(default_factory=set)
    ring_count: list[int] = field(default_factory=lambda: [0] * config.NUM_RINGS)


@dataclass
class Events:
    placed: list[tuple[int, int]] = field(default_factory=list)
    removed: list[tuple[int, int]] = field(default_factory=list)


class StateModel:
    def __init__(self) -> None:
        self.state = State()

    def update(self, occupied: set[tuple[int, int]]) -> tuple[State, Events]:
        prev = self.state.occupied
        events = Events(
            placed=sorted(occupied - prev),
            removed=sorted(prev - occupied),
        )
        counts = [0] * config.NUM_RINGS
        for ring, _slc in occupied:
            if 0 <= ring < config.NUM_RINGS:
                counts[ring] += 1
        self.state = State(occupied=set(occupied), ring_count=counts)
        return self.state, events
