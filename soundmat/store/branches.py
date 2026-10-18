"""状态树的分段，以及每一段唯一的写入者（CONTROL_API「状态树」）。

每段只由一个模块写：模块启动时用 ``Store.writer(...)`` 领取自己的段，别的模块只能读。
这样看板上的任何一个数，都能从这里直接找到是谁写的。新增一段时先在这里登记。
"""
from __future__ import annotations

BRANCHES: dict[str, str] = {
    "settings": "设置（store/settings.py）",
    "catalog.arrangements": "编排目录（sonification/catalog.py）",
    "catalog.recordings": "录制列表（recorder）",
    "status.current": "当前编排、模式状态、切换进度、电平条（sonification）",
    "status.engine": "声音引擎的声部数与计数（sonification）",
    "status.assets": "当前编排用到的声音素材（sonification）",
    "status.recording": "录制（recorder）",
    "status.update": "软件更新（updater）",
    "status.maintenance": "能否从控制台重启（maintenance.py）",
    "status.log": "最近的警告和错误（monitor/log.py）",
    "status.health": "状态指示（monitor）",
    "status.mat": "控制器链路（monitor）",
    "status.matHistory": "最近 60 秒的传感帧率（monitor）",
    "status.audio": "音频链路：音频服务、声卡、合成器服务（monitor）",
    "status.machine": "机器（monitor）",
    "status.network": "网络（monitor）",
    "status.rates": "各条链路的帧率（monitor）",
    "status.timing": "节拍延迟与计数（monitor）",
    "status.program": "主机程序：运行时间、重启、版本（monitor）",
    "status.storage": "录音空间（monitor）",
}


def branch_of(path: str) -> str | None:
    """路径属于哪一段；不属于任何登记过的段时为 None。"""
    for b in BRANCHES:
        if path == b or path.startswith(b + "."):
            return b
    return None
