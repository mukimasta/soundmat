"""软件更新：从 GitHub 下载发布包，安装成一个新版本目录，切换后重启（DEPLOYMENT「发布与更新」）。

装置上的程序目录按版本存放：``<base>/releases/<短提交号>/``，``<base>/current`` 指向正在用的版本，
systemd 从 ``current`` 启动主机程序。更新在后台完成：下载 → 核对 SHA-256 → 解压 → ``uv sync``，
全部成功后才原子地切换 ``current``，写下待确认的新版本和上一版，然后让主机程序退出，由 systemd 按新版本
重新启动。新版本正常运行 60 秒后确认；反复启动失败时，systemd 启动前运行的 ``soundmat-guard`` 会切回上一版。

只有从 ``releases/`` 里、在 systemd 下运行时才能更新（开发机上不能）。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..config import ROOT
from ..errors import Conflict
from ..store import Store
from .package import TAG_PREFIX, extract_package, parse_release_body, sha256_of

log = logging.getLogger("soundmat.update")

CONFIRM_AFTER = 60.0     # 秒：新版本正常运行这么久后确认
KEEP_OTHERS = 1          # 除当前版本和上一版之外，再保留几个旧版本目录
API = "https://api.github.com"


@dataclass(frozen=True)
class Layout:
    base: Path           # 包含 releases/ 和 current 的目录

    @property
    def releases(self) -> Path:
        return self.base / "releases"

    @property
    def current(self) -> Path:
        return self.base / "current"

    def current_name(self) -> str | None:
        try:
            return Path(os.readlink(self.current)).name
        except OSError:
            return None


def detect_layout(root: Path = ROOT) -> Layout | None:
    """程序是不是从 ``<base>/releases/<版本>/`` 运行、并且有 ``current`` 链接。"""
    if root.parent.name == "releases" and (root.parent.parent / "current").is_symlink():
        return Layout(root.parent.parent)
    return None


def switch_link(layout: Layout, name: str) -> None:
    """原子地把 ``current`` 指向 ``releases/<name>``（先建临时链接再替换）。"""
    tmp = layout.base / f".current.{os.getpid()}"
    if tmp.is_symlink():
        tmp.unlink()
    os.symlink(Path("releases") / name, tmp)
    os.replace(tmp, layout.current)


class Updater:
    def __init__(self, store: Store, events, repo: str, data_dir: Path, version: str | None,
                 layout: Layout | None = None, systemd: bool | None = None,
                 restart: Callable[[], None] | None = None,
                 fetch_json: Callable[[str], object] | None = None,
                 download: Callable[[str, Path], None] | None = None,
                 install_env: Callable[[Path], None] | None = None):
        self.store = store.writer("status.update")
        self.events = events
        self.repo = repo
        self.state_file = data_dir / "update.json"
        self.version = version                       # 正在运行的短提交号
        self.layout = layout
        self.systemd = bool(os.environ.get("INVOCATION_ID")) if systemd is None else systemd
        self.restart = restart or (lambda: None)
        self.fetch_json = fetch_json or _fetch_json
        self.download = download or _download
        self.install_env = install_env or _uv_sync
        self._lock = threading.Lock()
        self._busy = False
        self._timer: threading.Timer | None = None
        self._publish("idle", "")

    # ── 状态 ────────────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self.layout is not None and self.systemd

    def _read_state(self) -> dict:
        try:
            return json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            return {}

    def _write_state(self, st: dict) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(st, indent=2))
        os.replace(tmp, self.state_file)

    def _publish(self, state: str, message: str) -> None:
        st = self._read_state()
        self.store.update({"status.update": {
            "enabled": self.enabled, "state": state, "message": message,
            "previous": st.get("previous"), "failed": st.get("failed"), "pending": st.get("pending"),
        }})

    # ── 可安装的版本 ────────────────────────────────────────────────────

    def available(self, limit: int = 30) -> list[dict]:
        """GitHub 上的发布包，最新在前：tag、短提交号、分支、构建时间。"""
        data = self.fetch_json(f"{API}/repos/{self.repo}/releases?per_page={limit}")
        out = []
        for r in data if isinstance(data, list) else []:
            if not r.get("tag_name", "").startswith(TAG_PREFIX):
                continue
            meta = parse_release_body(r.get("body") or "")
            out.append({"tag": r["tag_name"], "commit": r["tag_name"][len(TAG_PREFIX):],
                        "branch": meta.get("branch"), "builtAt": meta.get("built"),
                        "current": r["tag_name"][len(TAG_PREFIX):] == self.version})
        out.sort(key=lambda x: x["builtAt"] or "", reverse=True)
        return out

    # ── 更新与回退 ──────────────────────────────────────────────────────

    def start_update(self, tag: str) -> None:
        """在后台安装 ``tag`` 并切换过去。不能更新或正在更新时抛出 ``UpdateError``。"""
        self._claim()
        threading.Thread(target=self._run_update, args=(tag,), name="update", daemon=True).start()

    def rollback(self) -> None:
        """切回上一版并重启。"""
        self._claim()
        try:
            prev = self._read_state().get("previous")
            if not prev or not (self.layout.releases / prev).is_dir():
                raise UpdateError("没有可以回到的上一版")
            self._switch(prev, f"回到上一版 {prev}")
        except Exception:
            with self._lock:
                self._busy = False
            raise

    def _claim(self) -> None:
        if not self.enabled:
            raise UpdateError("只有装置上（从发布包安装、由 systemd 运行时）才能更新")
        with self._lock:
            if self._busy:
                raise UpdateError("正在更新")
            self._busy = True

    def _run_update(self, tag: str) -> None:
        name = tag[len(TAG_PREFIX):] if tag.startswith(TAG_PREFIX) else tag
        try:
            if name == self.version:
                raise UpdateError(f"已经在运行 {name}")
            target = self.layout.releases / name
            if not (target / ".ready").exists():
                self._install(tag, name, target)
            self._switch(name, f"更新到 {name}")
        except Exception as e:
            log.exception("更新失败")
            self.events.error(f"更新到 {name} 失败：{e}")
            self._publish("error", str(e))
            with self._lock:
                self._busy = False

    def _install(self, tag: str, name: str, target: Path) -> None:
        self._publish("downloading", f"下载 {name}")
        rel = self.fetch_json(f"{API}/repos/{self.repo}/releases/tags/{tag}")
        assets = [a for a in rel.get("assets", []) if a.get("name", "").endswith(".tar.gz")]
        if not assets:
            raise UpdateError(f"{tag} 没有发布包")
        want = parse_release_body(rel.get("body") or "").get("sha256")
        self.layout.releases.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.layout.base) as tmp:
            archive = Path(tmp) / assets[0]["name"]
            self.download(assets[0]["browser_download_url"], archive)
            got = sha256_of(archive)
            if want and got != want:
                raise UpdateError("发布包校验失败（SHA-256 不一致）")
            self._publish("installing", f"安装 {name}")
            # 环境（.venv）里的脚本和路径写死了所在目录，所以先放到最终位置再建环境；
            # 只有建好之后才写 .ready，没有 .ready 的目录下次会重新安装
            shutil.rmtree(target, ignore_errors=True)
            extract_package(archive, target)
            try:
                self.install_env(target)
            except Exception:
                shutil.rmtree(target, ignore_errors=True)
                raise
            (target / ".ready").write_text(got + "\n")

    def _switch(self, name: str, message: str) -> None:
        current = self.layout.current_name()
        st = self._read_state()
        # plannedAt：这次退出是更新安排的，系统监测据此不把接下来的重启当成出错
        st.update({"pending": name, "previous": current, "attempts": 0, "plannedAt": time.time()})
        st.pop("failed", None)
        self._write_state(st)
        switch_link(self.layout, name)
        self._prune(keep={name, current})
        self.events.info(f"{message}，重新启动")
        self._publish("restarting", f"{message}，重新启动")
        self.restart()

    def _prune(self, keep: set) -> None:
        dirs = [d for d in self.layout.releases.iterdir() if d.is_dir() and not d.name.startswith(".")]
        others = sorted((d for d in dirs if d.name not in keep), key=lambda d: d.stat().st_mtime, reverse=True)
        for d in others[KEEP_OTHERS:]:
            shutil.rmtree(d, ignore_errors=True)

    # ── 启动后的确认 ────────────────────────────────────────────────────

    def confirm_if_pending(self) -> None:
        """新版本正常运行一段时间后调用：清除待确认标记，以后不会再被回退。"""
        st = self._read_state()
        if st.get("pending") and st["pending"] == self.version:
            st["pending"] = None
            st["attempts"] = 0
            self._write_state(st)
            self.events.info(f"新版本 {self.version} 运行正常")
            self._publish("idle", "")

    def start(self) -> None:
        """主机程序启动后：报告上次是否被自动回退，``CONFIRM_AFTER`` 秒后确认新版本。不能更新时什么都不做。"""
        if not self.enabled:
            return
        self._timer = threading.Timer(CONFIRM_AFTER, self.confirm_if_pending)
        self._timer.daemon = True
        self._timer.start()
        failed = self._read_state().get("failed")
        if failed:
            self.events.warning(f"版本 {failed} 启动失败，已回到 {self.version}")

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.cancel()


class UpdateError(Conflict):
    """不能更新的原因，直接显示给人看。"""


def _fetch_json(url: str) -> object:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "soundmat-updater"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "soundmat-updater"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def _uv_sync(release: Path) -> None:
    uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
    p = subprocess.run([uv, "sync", "--frozen", "--no-dev", "--quiet"], cwd=release,
                       capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        raise UpdateError(f"安装依赖失败：{(p.stderr or p.stdout).strip()[-400:]}")
