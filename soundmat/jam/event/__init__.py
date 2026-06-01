"""事件层（核心音乐逻辑）。三个 engine 并行：

- SensorState：传感矩阵 → 石头集合 + 放/拿边沿 + R0/R1 控制值（Lo-Fi + 开始/停止）
- HarmonyEngine：和声 pad 自动循环（每小节起点换和弦）
- DrumEngine：鼓自动循环（按 16 分网格 + 曲式 A/B/C/D）
- EventEngine：旋律 + bass，响应扫描线扫中石头
"""

from .sensor_state import SensorState, SensorDelta
from .harmony_engine import HarmonyEngine
from .drum_engine import DrumEngine
from .event_engine import EventEngine

__all__ = ["SensorState", "SensorDelta", "HarmonyEngine", "DrumEngine", "EventEngine"]
