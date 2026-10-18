"""装置需要的声音素材：所有编排实际引用到的文件（DEPLOYMENT「声音素材」）。

素材不经过 GitHub，由发布命令从开发机直接同步到装置；只同步被引用的文件（素材库里还有原始录音和
待整理的素材，装置用不到），不删除装置上已有的文件。
"""
from __future__ import annotations

from pathlib import Path

from ..sonification.arrangements import ARRANGEMENTS_DIR, discover
from ..sonification.mode import LoadError, ModeContext


def referenced_samples(arrangements_dir: Path = ARRANGEMENTS_DIR) -> tuple[list[str], list[str]]:
    """返回（所有编排引用的素材路径，相对于素材库的 ``samples/``，排好序；读取出错的编排说明）。"""
    from ..supervisor import MODES   # 避免循环导入

    found, errors = discover(arrangements_dir)
    refs: set[str] = set()
    for a in found.values():
        factory = MODES.get(a.mode)
        if factory is None:
            errors.append(f"{a.id}：没有名为 {a.mode} 的模式")
            continue
        try:
            refs |= factory(a, ModeContext(led_count=108)).load().assets
        except LoadError as e:
            errors.append(f"{a.id}：{e}")
    return sorted(refs), errors
