#!/usr/bin/env python3
"""在开发机上发布一个版本，并让装置更新到它（docs/implementation/DEPLOYMENT.md「发布与更新」）。

    uv run python scripts/release.py [--device soundmat-pi] [--no-update]

依次：检查工作区没有未提交的改动 → 推送当前分支 → 编译音色（源码没变时跳过）→ 构建控制台 →
打包 → 作为 GitHub 预发布版本 build-<短提交号> 的附件上传（已存在时跳过）→ 删除最近 20 个以外的旧版本 →
通过 Tailscale 通知装置更新，等它报告新版本已运行。需要 gh（已登录）和 npm。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from soundmat.updater.package import TAG_PREFIX, BuildInfo, build_package  # noqa: E402

KEEP = 20
STAMP = ROOT / "instruments" / "compiled" / ".source-hash"


def run(*args: str, capture: bool = False, cwd: Path = ROOT) -> str:
    p = subprocess.run(args, cwd=cwd, text=True, capture_output=capture)
    if p.returncode != 0:
        if capture:
            sys.stderr.write(p.stdout + p.stderr)
        sys.exit(f"失败：{' '.join(args)}")
    return p.stdout.strip() if capture else ""


def step(text: str) -> None:
    print(f"→ {text}", flush=True)


def repo_slug() -> str:
    url = run("git", "remote", "get-url", "origin", capture=True)
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    if not m:
        sys.exit(f"origin 不是 GitHub 仓库：{url}")
    return m.group(1)


def instruments_hash() -> str:
    h = hashlib.sha256()
    for p in sorted((ROOT / "instruments").rglob("*.scd")):
        h.update(str(p.relative_to(ROOT)).encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def compile_instruments() -> None:
    want = instruments_hash()
    compiled = ROOT / "instruments" / "compiled"
    if STAMP.exists() and STAMP.read_text().strip() == want and any(compiled.rglob("*.scsyndef")):
        step("音色没有变化，跳过编译")
        return
    step("编译音色")
    run(sys.executable, "scripts/compile_instruments.py")
    STAMP.write_text(want + "\n")


def build_console() -> None:
    console = ROOT / "console"
    if not (console / "node_modules").is_dir():
        step("安装控制台依赖")
        run("npm", "ci", cwd=console)
    step("构建控制台")
    run("npm", "run", "build", "--silent", cwd=console, capture=True)


def upload(repo: str, info: BuildInfo, archive: Path, sha256: str) -> None:
    exists = subprocess.run(["gh", "release", "view", info.tag, "--repo", repo],
                            capture_output=True, text=True).returncode == 0
    if exists:
        step(f"GitHub 上已有 {info.tag}，跳过上传")
        return
    step(f"上传到 GitHub：{info.tag}")
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as notes:
        notes.write(info.release_body(sha256))
    run("gh", "release", "create", info.tag, str(archive), "--repo", repo, "--prerelease",
        "--target", info.commit, "--title", f"build {info.short} ({info.branch})", "--notes-file", notes.name)


def prune(repo: str) -> None:
    out = run("gh", "api", f"repos/{repo}/releases?per_page=100", capture=True)
    builds = [r for r in json.loads(out) if r["tag_name"].startswith(TAG_PREFIX)]
    builds.sort(key=lambda r: r["created_at"], reverse=True)
    for r in builds[KEEP:]:
        step(f"删除旧版本 {r['tag_name']}")
        run("gh", "release", "delete", r["tag_name"], "--repo", repo, "--yes", "--cleanup-tag", capture=True)


def http(method: str, url: str, body: dict | None = None, timeout: float = 5.0) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def notify(device: str, port: int, info: BuildInfo) -> None:
    base = f"http://{device}:{port}"
    step(f"通知装置 {device} 更新到 {info.short}")
    try:
        http("POST", f"{base}/api/update", {"tag": info.tag})
    except urllib.error.HTTPError as e:
        sys.exit(f"装置拒绝了更新（{e.code}）：{e.read().decode(errors='replace')}")
    except OSError as e:
        sys.exit(f"连不上装置 {base}：{e}。发布包已在 GitHub 上，可以稍后在控制台的「软件更新」里安装。")
    last = None
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        time.sleep(1)
        try:
            st = http("GET", f"{base}/api/state", timeout=3).get("status", {})
        except OSError:
            if last != "restarting":
                print("  装置正在重启…", flush=True)
                last = "restarting"
            continue
        version = ((st.get("program") or {}).get("version") or {}).get("commit")
        upd = st.get("update") or {}
        if version == info.short and upd.get("state") in (None, "idle"):
            print(f"✓ 装置已运行 {info.short}", flush=True)
            return
        state = upd.get("state")
        if state and state != last:
            print(f"  {upd.get('message') or state}", flush=True)
            last = state
        if state == "error":
            sys.exit("装置更新失败，仍在运行原来的版本")
    sys.exit("等了 3 分钟，装置还没有报告新版本；请在控制台的看板上查看")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", default="soundmat-pi", help="装置的名字或地址（Tailscale），默认 soundmat-pi")
    ap.add_argument("--port", type=int, default=8000, help="装置控制接口的端口")
    ap.add_argument("--no-update", action="store_true", help="只发布到 GitHub，不通知装置")
    args = ap.parse_args()

    if run("git", "status", "--porcelain", "--untracked-files=no", capture=True):
        sys.exit("有未提交的改动：发布的版本必须对应一个提交，请先提交")
    branch = run("git", "rev-parse", "--abbrev-ref", "HEAD", capture=True)
    commit = run("git", "rev-parse", "HEAD", capture=True)
    info = BuildInfo(commit, branch, datetime.now().astimezone().isoformat(timespec="seconds"))
    repo = repo_slug()

    step(f"推送 {branch}（{info.short}）")
    run("git", "push", "--quiet", "-u", "origin", branch)
    compile_instruments()
    build_console()
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / f"soundmat-{info.short}.tar.gz"
        step("打包")
        sha = build_package(ROOT, archive, info)
        print(f"  {archive.stat().st_size / 1024:.0f} KB · sha256 {sha[:12]}…", flush=True)
        upload(repo, info, archive, sha)
    prune(repo)
    if args.no_update:
        print(f"✓ 已发布 {info.tag}", flush=True)
        return
    notify(args.device, args.port, info)


if __name__ == "__main__":
    main()
