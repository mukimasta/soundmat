"""scripts/compile_instruments.py：只在 Linux 上给 sclang 设置无桌面的 Qt 平台。"""
import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load():
    spec = importlib.util.spec_from_file_location("compile_instruments", ROOT / "scripts" / "compile_instruments.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_with(monkeypatch, platform, env=None):
    mod = load()
    seen = {}

    def fake_run(args, cwd, env, capture_output, text, timeout):
        seen.update(env)
        return subprocess.CompletedProcess(args, 1, "", "")

    monkeypatch.setattr(mod.sys, "platform", platform)
    monkeypatch.setattr(mod, "find_sclang", lambda: "/usr/bin/sclang")
    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    for k in ("QT_QPA_PLATFORM", "QTWEBENGINE_DISABLE_SANDBOX"):
        monkeypatch.delenv(k, raising=False)
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    mod.main()
    return seen


def test_linux_defaults_to_offscreen(monkeypatch):
    env = run_with(monkeypatch, "linux")
    assert env["QT_QPA_PLATFORM"] == "offscreen"


def test_macos_leaves_qt_platform_alone(monkeypatch):
    env = run_with(monkeypatch, "darwin")
    assert "QT_QPA_PLATFORM" not in env and "QTWEBENGINE_DISABLE_SANDBOX" not in env


def test_explicit_setting_wins(monkeypatch):
    assert run_with(monkeypatch, "linux", {"QT_QPA_PLATFORM": "xcb"})["QT_QPA_PLATFORM"] == "xcb"
