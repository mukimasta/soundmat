"""OSC 客户端封装：向 scsynth 发节点指令。

构建在 `supercollider` 库的 Server 之上（它管 OSC 传输与 /sync），但节点创建/调参/释放
走原始 OSC（/s_new、/n_set、/n_free、/g_new、/g_deepFree），以便我们自己掌控节点 ID
分配与分组——模式停止时 `/n_free` 整个 group 即可一次性干净杀光所有 synth。

节点 ID 从 100000 起自增分配，避开库给 Buffer 等分配的低号段。
"""
from __future__ import annotations

import itertools
import threading

# 与 SuperCollider 服务器约定的 addAction 常量
ADD_TO_HEAD = 0
ADD_TO_TAIL = 1
ADD_BEFORE = 2
ADD_AFTER = 3
ADD_REPLACE = 4

ROOT_NODE = 0
DEFAULT_GROUP = 1


class OSCClient:
    """薄封装：节点 ID 分配 + 常用 server 指令。"""

    def __init__(self, server):
        self.server = server
        self._ids = itertools.count(100000)
        self._lock = threading.Lock()

    def alloc_id(self) -> int:
        with self._lock:
            return next(self._ids)

    # ── 原始发送 ──
    def send(self, address: str, *args) -> None:
        self.server._send_msg(address, *args)

    def sync(self) -> None:
        self.server.sync()

    # ── 分组 ──
    def new_group(self, target: int = ROOT_NODE, add_action: int = ADD_TO_TAIL) -> int:
        # 注意：裸 scsynth（非经 sclang 启动）没有默认 group 1，只有 root node 0 恒存在。
        # 故模式 group 默认挂在 root node 0 下。
        gid = self.alloc_id()
        self.send("/g_new", gid, add_action, target)
        return gid

    def free_node(self, node_id: int) -> None:
        """释放节点；若是 group，连同其全部子节点一并释放。"""
        self.send("/n_free", node_id)

    def deep_free_group(self, group_id: int) -> None:
        """释放 group 内所有 synth，但保留 group 节点本身。"""
        self.send("/g_deepFree", group_id)

    # ── synth ──
    @staticmethod
    def _flatten_params(params: dict) -> list:
        flat: list = []
        for key, value in params.items():
            # Buffer 对象 → bufnum
            bufnum = getattr(value, "id", None)
            if bufnum is not None and value.__class__.__name__ == "Buffer":
                value = bufnum
            flat.extend([key, float(value) if isinstance(value, bool) else value])
        return flat

    def new_synth(
        self,
        synthdef: str,
        params: dict | None = None,
        *,
        target: int = DEFAULT_GROUP,
        add_action: int = ADD_TO_HEAD,
    ) -> int:
        """实例化一个 synth，返回其节点 ID。即发即用，调参用 set_node。"""
        node_id = self.alloc_id()
        args = [synthdef, node_id, add_action, target]
        if params:
            args.extend(self._flatten_params(params))
        self.send("/s_new", *args)
        return node_id

    def set_node(self, node_id: int, **params) -> None:
        if not params:
            return
        self.send("/n_set", node_id, *self._flatten_params(params))

    def set_group_param(self, group_id: int, **params) -> None:
        """对 group 内所有节点统一设参（/n_set 对 group 递归生效）。"""
        self.set_node(group_id, **params)
