"""scsynth 进程管理 + .scsyndef 加载 + group 分配。

封装 `supercollider` 库做*必要*的事：scsynth 进程生命周期、加载编译好的 def、读 buffer、
建/毁 group。所有“什么时候响什么”的逻辑在模式层；这里只提供句柄。

模式隔离（设计文档 §8）：每个模式启动时 `new_group()` 新建一个 SC group，自己的 synth
全 spawn 在这个 group 下；停止时 `free_group()` 一次 `/n_free` 整个 group，声音立刻干净消失。
"""
from __future__ import annotations

import subprocess
import threading

from .. import config
from .osc import ADD_TO_TAIL, ROOT_NODE, OSCClient


class SCServerHandle:
    def __init__(self, port: int | None = None, scsynth_path: str | None = None, response_timeout: float = 30.0):
        self.port = port or config.SC_PORT
        self.scsynth_path = scsynth_path or config.SCSYNTH_PATH
        self.response_timeout = response_timeout
        self.proc: subprocess.Popen | None = None
        self.server = None
        self.osc: OSCClient | None = None

    # ── 生命周期 ──
    def boot(self, timeout: float = 10.0) -> "SCServerHandle":
        """启动 scsynth 并连接。-i 0 关输入避开采样率冲突，-o 2 立体声输出。"""
        from supercollider import Server
        from supercollider import globals as sc_globals

        self.proc = subprocess.Popen(
            [
                self.scsynth_path,
                "-u", str(self.port),
                "-i", "0",
                "-o", "2",
                "-S", str(config.SAMPLE_RATE),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        ready = threading.Event()

        def _watch():
            assert self.proc and self.proc.stdout
            for line in self.proc.stdout:
                print("[scsynth]", line.rstrip())
                if "server ready" in line:
                    ready.set()

        threading.Thread(target=_watch, daemon=True).start()
        if not ready.wait(timeout):
            self.quit()
            raise RuntimeError("scsynth 未在超时内就绪（端口占用？设备采样率冲突？）")

        sc_globals.RESPONSE_TIMEOUT = self.response_timeout
        self.server = Server(hostname=config.SC_HOST, port=self.port)
        self.osc = OSCClient(self.server)
        return self

    def quit(self) -> None:
        if self.server is not None:
            try:
                self.server._send_msg("/quit")
            except Exception:
                pass
            self.server = None
            self.osc = None
        if self.proc is not None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except Exception:
                self.proc.kill()
            self.proc = None

    def __enter__(self):
        return self.boot()

    def __exit__(self, *exc):
        self.quit()

    # ── 资源加载 ──
    def load_synthdefs(self, directory=None) -> None:
        """把目录下所有 .scsyndef 加载进 scsynth（启动时一次性加载两个模式的全部 def）。"""
        directory = str(directory or config.COMPILED_DIR)
        self.server._send_msg("/d_loadDir", directory)
        self.server.sync()

    def read_buffer(self, path):
        """读音频文件成 buffer，返回库的 Buffer（含 num_channels/num_frames）。"""
        from supercollider import Buffer

        buf = Buffer.read(self.server, str(path))
        info = buf.get_info()
        buf.num_frames = info["num_frames"]
        buf.num_channels = info["num_channels"]
        return buf

    # ── group 隔离 ──
    def new_group(self, target: int = ROOT_NODE, add_action: int = ADD_TO_TAIL) -> int:
        assert self.osc is not None
        return self.osc.new_group(target=target, add_action=add_action)

    def free_group(self, group_id: int) -> None:
        """杀光 group 下所有 synth 并释放 group 本身。"""
        assert self.osc is not None
        self.osc.free_node(group_id)
