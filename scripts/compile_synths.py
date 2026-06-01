#!/usr/bin/env python
"""调用 sclang 编译 SynthDef → sc/compiled/*.scsyndef。

用法：uv run python scripts/compile_synths.py
等价于：sclang sc/compile.scd（离线序列化，不启动 scsynth）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from soundmat import config  # noqa: E402


def main() -> int:
    compile_scd = config.SC_DIR / "compile.scd"
    if not compile_scd.exists():
        print(f"找不到 {compile_scd}")
        return 1
    print(f"编译 SynthDef：{config.SCLANG_PATH} {compile_scd}")
    try:
        proc = subprocess.run([config.SCLANG_PATH, str(compile_scd)], cwd=str(ROOT))
    except FileNotFoundError:
        print(f"找不到 sclang：{config.SCLANG_PATH}（设环境变量 SOUNDMAT_SCLANG 覆盖）")
        return 1
    produced = sorted(config.COMPILED_DIR.glob("*.scsyndef"))
    print(f"产物 {len(produced)} 个：" + ", ".join(p.stem for p in produced))
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
