"""每个模块都能单独导入：模块之间没有循环导入（之前设置模块、声音引擎和声音化之间有过一个）。"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_every_module_imports_on_its_own():
    mods = sorted(".".join(p.relative_to(ROOT).with_suffix("").parts).removesuffix(".__init__")
                  for p in (ROOT / "soundmat").rglob("*.py"))
    code = "import importlib, sys\nfor m in sys.argv[1:]:\n    importlib.import_module(m)\n    [sys.modules.pop(k) for k in list(sys.modules) if k.startswith('soundmat')]\n"
    r = subprocess.run([sys.executable, "-c", code, *mods], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
