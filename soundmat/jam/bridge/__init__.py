"""桥层：把抽象音乐事件翻译成 OSC，在此处应用 ring → instrument 映射与级数 → freq 解析。

- SynthBridge：NoteEvent / ChordEvent → /s_new（旋律、bass、鼓、和声 pad）
- MasterFX：ParamEvent（Lo-Fi 强度）→ master FX synth 调参
"""

from .synth_bridge import SynthBridge
from .master_fx import MasterFX

__all__ = ["SynthBridge", "MasterFX"]
