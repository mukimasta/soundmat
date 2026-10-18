"""发布包：装置运行一个版本所需的全部文件（DEPLOYMENT「发布与更新」）。

发布包由开发机构建，作为 GitHub 预发布版本的附件存放；装置下载后解压即可运行，不做任何构建。
GitHub 上的说明（release body）用几行 ``键: 值`` 记录分支、提交号、构建时间和包的 SHA-256。
"""
from __future__ import annotations

import hashlib
import io
import tarfile
from dataclasses import dataclass
from pathlib import Path

TAG_PREFIX = "build-"
# 发布包里的内容（相对于仓库根目录）；编译好的音色和构建好的控制台不在 git 里，由开发机构建
CONTENTS = ("soundmat", "arrangements", "config", "instruments/compiled", "console/dist", "system",
            "pyproject.toml", "uv.lock")
SKIP = ("__pycache__", ".pyc", ".DS_Store")


@dataclass(frozen=True)
class BuildInfo:
    commit: str          # 完整提交号
    branch: str
    built_at: str        # ISO 8601，带时区

    @property
    def short(self) -> str:
        return self.commit[:7]

    @property
    def tag(self) -> str:
        return TAG_PREFIX + self.short

    def version_file(self) -> str:
        """装置上的 VERSION 文件：提交号、构建时间、分支，各一行（看板据此显示版本）。"""
        return f"{self.short}\n{self.built_at}\n{self.branch}\n"

    def release_body(self, sha256: str) -> str:
        return (f"branch: {self.branch}\ncommit: {self.commit}\nbuilt: {self.built_at}\nsha256: {sha256}\n")


def parse_release_body(body: str) -> dict[str, str]:
    out = {}
    for line in (body or "").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _skip(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    if any(s in info.name for s in SKIP):
        return None
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    return info


def build_package(root: Path, out: Path, info: BuildInfo) -> str:
    """把发布包写到 ``out``，返回它的 SHA-256。缺少编译好的音色或控制台时报错。"""
    for rel in CONTENTS:
        if not (root / rel).exists():
            raise FileNotFoundError(f"发布包缺少 {rel}（编译音色、构建控制台了吗？）")
    with tarfile.open(out, "w:gz") as tar:
        for rel in CONTENTS:
            tar.add(root / rel, arcname=rel, filter=_skip)
        data = info.version_file().encode()
        ti = tarfile.TarInfo("VERSION")
        ti.size = len(data)
        tar.addfile(ti, io.BytesIO(data))
    return sha256_of(out)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_package(archive: Path, dest: Path) -> None:
    """解压发布包到 ``dest``（只接受普通文件和目录，拒绝跳出目标目录的路径）。"""
    dest.mkdir(parents=True)
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(dest, filter="data")
