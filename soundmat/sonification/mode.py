"""模式：一类交互逻辑的实现（SONIFICATION「模式的生命周期」）。

一个模式实例加载一份编排，经历 加载 → 开始 → 每一拍 → 停止。模式只使用节拍提供的时间，
不读取系统时钟，也不接触任何设备，所以在开发机、测试和装置上行为一致。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from ..clock import Beat
from ..perception.model import MatEvent, MatSnapshot
from ..errors import UserError
from ..intent import BeatOutput


class LoadError(UserError):
    """编排不符合模式的要求，或引用无法满足。消息直接显示给人看。"""


@dataclass(frozen=True)
class Arrangement:
    """编排：交给模式的内容数据（DATA_MODEL「编排」）。头部字段之外的内容放在 ``content``。"""
    id: str
    title: str
    mode: str
    description: str = ""
    mode_label: str = ""                      # 控制台显示的模式说明，例如 "Ambient · 氛围"
    ring_labels: tuple[str, ...] = ()         # 每环在控制台上显示的名字
    meters: Mapping[str, Any] = field(default_factory=dict)  # 电平条声明（[meters]），见 sonification/meters.py
    level: float = 0.0                        # 整体电平（dB）：这份编排的混音总增益，用来对齐各编排的响度
    content: Mapping[str, Any] = field(default_factory=dict)
    path: str | None = None                   # 编排所在文件夹


@dataclass(frozen=True)
class LoadPlan:
    """模式加载时向外声明的需求。"""
    assets: frozenset[str] = frozenset()      # 需要的声音素材（素材库内相对路径）
    instruments: frozenset[str] = frozenset() # 需要的音色
    features: frozenset[str] = frozenset()    # 需要感知提供的特征
    control_zones: frozenset[int] = frozenset()  # 控制区
    buses: tuple[str, ...] = tuple(f"ring{r}" for r in range(8))  # 混音结构里的总线
    lookahead: float = 0.0                    # 前瞻时间窗的提前量（秒）
    fx: str = "sm_fx_freeverb"                # 共用效果的音色


def _no_settings(path: str, default: Any = None) -> Any:
    return default


def _no_report(key: str) -> list[float] | None:
    return None


@dataclass(frozen=True)
class ModeContext:
    led_count: int
    # 读取当前设置（点号路径，相对于 settings），例如 setting("sound.layout")
    setting: Callable[[str, Any], Any] = _no_settings
    # 随机数种子；None 表示每次运行不同（测试中固定）
    seed: int | None = None
    # 有确定时刻的声音比给出的时刻晚多少秒被听到（sound.schedule_ahead）；灯光要和这些声音同步时按它推后
    heard_after: float = 0.0
    # 读取这个模式实例的某个持续声部（按标识）的音色送回来的最新测量值；没有时为 None。
    # 声音化里唯一从声音读回的通道，目前只有声池模式的灯光用它跟随底音（SONIFICATION「声池模式的运行」）
    report: Callable[[str], "list[float] | None"] = _no_report


class Mode(ABC):
    name: str = ""

    def __init__(self, arrangement: Arrangement, ctx: ModeContext):
        self.arrangement = arrangement
        self.ctx = ctx
        self.plan: LoadPlan = LoadPlan()

    @abstractmethod
    def load(self) -> LoadPlan:
        """检查编排，解析引用，声明需求。不满足时抛出 ``LoadError``。"""

    def start(self, t: float) -> None:
        """建立初始状态，从下一拍开始给出意图。"""

    @abstractmethod
    def tick(self, beat: Beat, snapshot: MatSnapshot, events: list[MatEvent]) -> BeatOutput:
        """根据最新输入交出这一拍完整的意图和模式状态。"""

    def stop(self) -> None:
        """不再被调用；留下的声音由声音引擎淡出，模式不需要收尾。"""
