"""MasterFX：Lo-Fi 强度（R0/R1）→ master FX synth 调参（设计文档 §6.2 / JAM_DESIGN §3）。

输入 0–1000（来自 R0/R1 压力）。按 lofi_mapping 的分段线性关键点曲线映射到 master synth
的参数（低通截止 cutoff、磁带饱和 drive）。默认曲线复刻 web demo：
cutoff = 14000·(420/14000)^(level/2000)，drive = level/40000（level 1000 → cutoff≈2425, drive=0.025）。

master synth 由 JamApp 在 group 内 ADD_TO_TAIL spawn，读三条总线做总线增益 + LPF + 磁带饱和
+ 限幅；这里持有它的节点 ID 调参。和声/鼓增益固定，不随石头数变化（JAM_DESIGN §3）。
"""
from __future__ import annotations

from ...core.osc import OSCClient


def _interp(keypoints: dict, x: float) -> float:
    """分段线性插值。keypoints: {输入: 输出}，键可为字符串。超界取端点值。"""
    pts = sorted((float(k), float(v)) for k, v in keypoints.items())
    if not pts:
        return 0.0
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            t = 0.0 if x1 == x0 else (x - x0) / (x1 - x0)
            return y0 + (y1 - y0) * t
    return pts[-1][1]


# 默认曲线（复刻 web demo），lofi_mapping.yaml 可覆盖
DEFAULT_MAPPING = {
    "cutoff": {0: 14000, 250: 9500, 500: 6447, 750: 4376, 1000: 2425},
    "drive": {0: 0.0, 250: 0.00625, 500: 0.0125, 750: 0.01875, 1000: 0.025},
}


class MasterFX:
    def __init__(
        self,
        osc: OSCClient,
        master_node: int,
        mapping: dict | None = None,
        master_volume: float = 1.0,
    ):
        self.osc = osc
        self.master_node = master_node
        self.mapping = mapping or DEFAULT_MAPPING
        self.master_volume = master_volume
        self._last_value: float | None = None

    def set_lofi(self, value: float) -> None:
        """value 0..1000 → cutoff/drive，n_set 到 master 节点。"""
        value = max(0.0, min(1000.0, value))
        if self._last_value is not None and abs(value - self._last_value) < 0.5:
            return
        self._last_value = value
        params = {}
        if "cutoff" in self.mapping:
            params["cutoff"] = _interp(self.mapping["cutoff"], value)
        if "drive" in self.mapping:
            params["drive"] = _interp(self.mapping["drive"], value)
        if params:
            self.osc.set_node(self.master_node, **params)

    def set_volume(self, volume: float) -> None:
        self.master_volume = max(0.0, min(1.0, volume))
        self.osc.set_node(self.master_node, amp=self.master_volume)
