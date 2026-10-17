#!/usr/bin/env python3
"""编译全部音色：uv run python scripts/compile_instruments.py

调用 sclang 运行 instruments/build.scd，产物写到 instruments/compiled/（2、4、8 声道各一份）。
sclang 的位置：环境变量 SOUNDMAT_SCLANG，否则 PATH 里的 sclang，否则 macOS 的 SuperCollider.app。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAC_SCLANG = "/Applications/SuperCollider.app/Contents/MacOS/sclang"


def find_sclang() -> str | None:
    env = os.environ.get("SOUNDMAT_SCLANG")
    if env:
        return env
    found = shutil.which("sclang")
    if found:
        return found
    return MAC_SCLANG if Path(MAC_SCLANG).exists() else None


def main() -> int:
    sclang = find_sclang()
    if sclang is None:
        print("找不到 sclang。安装 SuperCollider，或用环境变量 SOUNDMAT_SCLANG 指定。", file=sys.stderr)
        return 1
    env = dict(os.environ)
    if sys.platform.startswith("linux"):
        # 无桌面的 Linux（树莓派、CI、云端）里 sclang 也能运行。macOS 版 SuperCollider.app
        # 只带 cocoa 平台插件，设置 offscreen 会让 sclang 直接退出，所以只在 Linux 上设置。
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
        env.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    proc = subprocess.run([sclang, str(ROOT / "instruments" / "build.scd")], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=300)
    lines = [l for l in proc.stdout.splitlines() if "声道" in l or "完成" in l or "ERROR" in l]
    print("\n".join(lines) or proc.stdout[-2000:])
    compiled = sorted((ROOT / "instruments" / "compiled").glob("*.scsyndef"))
    if proc.returncode != 0 or not compiled:
        print(proc.stderr[-2000:], file=sys.stderr)
        return 1
    print(f"共 {len(compiled)} 个 SynthDef 文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
