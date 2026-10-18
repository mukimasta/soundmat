"""把一次录制的文件夹打包成 zip 下载：边打包边输出，不压缩，不需要临时文件。"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Iterator


class _Sink(io.RawIOBase):
    """zipfile 写入的不可回退流：写进去的字节由生成器取走。"""

    def __init__(self):
        self.chunks: list[bytes] = []

    def writable(self) -> bool:
        return True

    def write(self, b) -> int:
        self.chunks.append(bytes(b))
        return len(b)

    def take(self) -> bytes:
        out, self.chunks = b"".join(self.chunks), []
        return out


def zip_stream(folder: Path, chunk: int = 1 << 20) -> Iterator[bytes]:
    """把一次录制的文件夹边打包边输出（不压缩，不需要临时文件）。"""
    sink = _Sink()
    with zipfile.ZipFile(sink, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            arc = f"{folder.name}/{path.relative_to(folder)}"
            with open(path, "rb") as src, zf.open(arc, "w", force_zip64=True) as dst:
                while True:
                    data = src.read(chunk)
                    if not data:
                        break
                    dst.write(data)
                    yield sink.take()
            yield sink.take()
    yield sink.take()
