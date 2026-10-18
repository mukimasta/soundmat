"""软件更新：发布包、安装与切换、校验失败、回退、确认、启动保护、谁能更新。"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from soundmat.control import may_update
from soundmat.monitor.log import EventLog
from soundmat.store import Store
from soundmat.updater import Layout, Updater, UpdateError, detect_layout, switch_link
from soundmat.updater.package import CONTENTS, BuildInfo, build_package, extract_package, parse_release_body

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "system" / "update" / "soundmat-guard"


def fake_repo(tmp: Path) -> Path:
    """一个只有发布包所需目录结构的假仓库（CI 上没有编译好的音色和控制台）。"""
    repo = tmp / "repo"
    for rel in CONTENTS:
        p = repo / rel
        if "." in Path(rel).name:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x")
        else:
            p.mkdir(parents=True, exist_ok=True)
            (p / "file.txt").write_text(rel)
    (repo / "soundmat" / "__pycache__").mkdir()
    (repo / "soundmat" / "__pycache__" / "a.pyc").write_text("junk")
    return repo


def make_package(tmp: Path, commit: str = "bbbbbbb1234", branch: str = "master") -> tuple[Path, str, BuildInfo]:
    info = BuildInfo(commit, branch, "2026-10-17T16:30:00-07:00")
    out = tmp / f"soundmat-{info.short}.tar.gz"
    sha = build_package(fake_repo(tmp), out, info)
    return out, sha, info


def test_package_contents_and_body(tmp_path):
    archive, sha, info = make_package(tmp_path)
    dest = tmp_path / "x"
    extract_package(archive, dest)
    assert (dest / "VERSION").read_text() == "bbbbbbb\n2026-10-17T16:30:00-07:00\nmaster\n"
    assert (dest / "console" / "dist" / "file.txt").exists()
    assert not (dest / "soundmat" / "__pycache__").exists()
    assert parse_release_body(info.release_body(sha)) == {
        "branch": "master", "commit": "bbbbbbb1234", "built": "2026-10-17T16:30:00-07:00", "sha256": sha}
    assert info.tag == "build-bbbbbbb"


def test_package_refuses_without_build_outputs(tmp_path):
    repo = fake_repo(tmp_path)
    import shutil
    shutil.rmtree(repo / "console" / "dist")
    with pytest.raises(FileNotFoundError, match="console/dist"):
        build_package(repo, tmp_path / "p.tar.gz", BuildInfo("c" * 40, "x", "t"))


@pytest.fixture
def device(tmp_path):
    """装置上的目录结构：releases/aaaaaaa 是当前版本。"""
    base = tmp_path / "soundmat"
    (base / "releases" / "aaaaaaa").mkdir(parents=True)
    (base / "releases" / "aaaaaaa" / ".ready").write_text("x")
    os.symlink(Path("releases") / "aaaaaaa", base / "current")
    return Layout(base)


def make_updater(tmp_path, layout, archive=None, sha=None, info=None, systemd=True, restarts=None):
    store = Store({"status": {}})
    restarts = restarts if restarts is not None else []
    releases = []
    if info:
        releases.append({"tag_name": info.tag, "body": info.release_body(sha),
                         "assets": [{"name": archive.name, "browser_download_url": "https://x/" + archive.name}]})

    def fetch(url):
        if "/tags/" in url:
            return releases[0]
        return releases + [{"tag_name": "v1-ece546", "body": ""}]

    def download(url, dest):
        dest.write_bytes(archive.read_bytes())

    up = Updater(store, EventLog(store), "me/repo", tmp_path / "data", "aaaaaaa", layout=layout, systemd=systemd,
                 restart=lambda: restarts.append(1), fetch_json=fetch, download=download,
                 install_env=lambda d: (d / ".venv").mkdir())
    return up, store, restarts


def wait_state(store, *states, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if store.get("status.update.state") in states:
            return store.get("status.update.state")
        time.sleep(0.02)
    raise AssertionError(store.get("status.update"))


def test_update_installs_switches_and_restarts(tmp_path, device):
    archive, sha, info = make_package(tmp_path)
    up, store, restarts = make_updater(tmp_path, device, archive, sha, info)
    assert up.enabled
    assert [r["tag"] for r in up.available()] == ["build-bbbbbbb"]
    up.start_update(info.tag)
    assert wait_state(store, "restarting", "error") == "restarting"
    assert device.current_name() == "bbbbbbb"
    new = device.releases / "bbbbbbb"
    assert (new / ".ready").exists() and (new / ".venv").is_dir() and (new / "VERSION").exists()
    st = json.loads((tmp_path / "data" / "update.json").read_text())
    assert st == {"pending": "bbbbbbb", "previous": "aaaaaaa", "attempts": 0}
    assert restarts == [1]


def test_checksum_mismatch_keeps_current_version(tmp_path, device):
    archive, sha, info = make_package(tmp_path)
    up, store, restarts = make_updater(tmp_path, device, archive, "0" * 64, info)
    up.start_update(info.tag)
    assert wait_state(store, "error", "restarting") == "error"
    assert "SHA-256" in store.get("status.update.message")
    assert device.current_name() == "aaaaaaa" and restarts == []
    assert not (device.releases / "bbbbbbb").exists()


def test_failed_env_install_leaves_no_ready_release(tmp_path, device):
    archive, sha, info = make_package(tmp_path)
    up, store, restarts = make_updater(tmp_path, device, archive, sha, info)

    def broken(d):
        raise UpdateError("安装依赖失败：network")
    up.install_env = broken
    up.start_update(info.tag)
    assert wait_state(store, "error", "restarting") == "error"
    assert device.current_name() == "aaaaaaa"
    assert not (device.releases / "bbbbbbb").exists()


def test_rollback_and_confirm(tmp_path, device):
    (device.releases / "bbbbbbb").mkdir()
    switch_link(device, "bbbbbbb")
    up, store, restarts = make_updater(tmp_path, device)
    up.version = "bbbbbbb"
    up._write_state({"pending": "bbbbbbb", "previous": "aaaaaaa", "attempts": 1})
    up.confirm_if_pending()
    assert json.loads(up.state_file.read_text())["pending"] is None
    up.rollback()
    assert device.current_name() == "aaaaaaa" and restarts == [1]


def test_not_enabled_off_device(tmp_path, device):
    up, store, _ = make_updater(tmp_path, device, systemd=False)
    with pytest.raises(UpdateError, match="只有装置上"):
        up.start_update("build-x")
    assert store.get("status.update.enabled") is False
    assert detect_layout(ROOT) is None                      # 开发机上不是从 releases/ 运行


def test_detect_layout(device):
    assert detect_layout(device.releases / "aaaaaaa") == device


def run_guard(device, state_file):
    env = {**os.environ, "SOUNDMAT_HOME": str(device.base), "SOUNDMAT_UPDATE_STATE": str(state_file)}
    subprocess.run([sys.executable, str(GUARD)], env=env, check=True, capture_output=True)
    return json.loads(state_file.read_text())


def test_guard_rolls_back_after_repeated_failed_starts(tmp_path, device):
    (device.releases / "bbbbbbb").mkdir()
    switch_link(device, "bbbbbbb")
    state = tmp_path / "update.json"
    state.write_text(json.dumps({"pending": "bbbbbbb", "previous": "aaaaaaa", "attempts": 0}))
    for n in (1, 2, 3):
        assert run_guard(device, state)["attempts"] == n
        assert device.current_name() == "bbbbbbb"
    st = run_guard(device, state)                            # 第 4 次启动前：回到上一版
    assert device.current_name() == "aaaaaaa"
    assert st == {"pending": None, "failed": "bbbbbbb", "attempts": 0, "previous": None}


def test_guard_ignores_missing_or_confirmed_state(tmp_path, device):
    state = tmp_path / "update.json"
    env = {**os.environ, "SOUNDMAT_HOME": str(device.base), "SOUNDMAT_UPDATE_STATE": str(state)}
    assert subprocess.run([sys.executable, str(GUARD)], env=env).returncode == 0
    state.write_text(json.dumps({"pending": None, "previous": "aaaaaaa"}))
    assert run_guard(device, state) == {"pending": None, "previous": "aaaaaaa"}


@pytest.mark.parametrize("host, ok", [
    ("127.0.0.1", True), ("::1", True), ("100.108.24.120", True), ("::ffff:100.90.172.113", True),
    ("192.168.0.48", False), ("10.42.0.23", False), ("172.20.10.3", False), (None, False),
])
def test_only_local_or_tailscale_may_update(host, ok):
    assert may_update(host) is ok


def test_referenced_samples_are_what_arrangements_use():
    """发布时同步到装置的素材：所有编排引用到的文件，相对于素材库的 samples/。"""
    from soundmat.updater.samples import referenced_samples

    refs, errors = referenced_samples()
    assert errors == []
    assert refs == sorted(refs) and len(refs) == len(set(refs))
    assert refs and all(r.startswith("kyoto/") and r.endswith(".wav") for r in refs)   # Lo-Fi 全是合成音色
