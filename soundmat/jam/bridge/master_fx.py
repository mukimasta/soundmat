"""MasterFX：Lo-Fi 强度（R0/R1）→ master FX synth 调参（设计文档 §6.2 / JAM_DESIGN §3）。

输入 0–1000（来自 R0/R1 压力）。按 lofi_mapping 分段线性映射 cutoff / drive；
在 Python 侧指数平滑（~60 Hz Jam 主循环），SC 端用同一 cutoff 做全湿低通，避免
Lag.kr 与干/湿 mix 不同步导致 Lo-Fi 0/1000 听感错乱。
"""
from __future__ import annotations

from ...core.osc import OSCClient

# 主循环 ~60 Hz；α 按原 200 Hz 曲线换算，保持相近秒级跟手
_SMOOTH_ALPHA_UP = 0.38
_SMOOTH_ALPHA_DOWN = 0.68
_CUTOFF_SEND_EPS = 8.0
_DRIVE_SEND_EPS = 0.00005
_GAIN_SEND_EPS = 0.008


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


def _smooth_lofi_step(current: float, target: float) -> float:
    target = max(0.0, min(1000.0, target))
    alpha = _SMOOTH_ALPHA_DOWN if target < current else _SMOOTH_ALPHA_UP
    next_v = current + (target - current) * alpha
    if target <= 0.0 and next_v < 1.5:
        return 0.0
    if target >= 999.0 and next_v > 998.5:
        return 1000.0
    return max(0.0, min(1000.0, next_v))


# 默认曲线（复刻 web demo），lofi_mapping.yaml 可覆盖
DEFAULT_MAPPING = {
    "cutoff": {0: 14000, 250: 9500, 500: 6447, 750: 4376, 1000: 2425},
    "drive": {0: 0.0, 250: 0.00625, 500: 0.0125, 750: 0.01875, 1000: 0.025},
    # LPF + 饱和会掉电平；随 Lo-Fi 略补（1000 → +3.2 dB）
    "gain": {0: 1.0, 250: 1.08, 500: 1.16, 750: 1.24, 1000: 1.45},
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
        self._smooth: float | None = None
        self._sent_cutoff: float | None = None
        self._sent_drive: float | None = None
        self._sent_gain: float | None = None

    def set_lofi(self, value: float) -> None:
        """value 0..1000 → 平滑 → cutoff/drive，n_set 到 master 节点。"""
        target = max(0.0, min(1000.0, value))
        if self._smooth is None:
            self._smooth = target
        else:
            self._smooth = _smooth_lofi_step(self._smooth, target)

        cutoff = _interp(self.mapping["cutoff"], self._smooth)
        drive = _interp(self.mapping["drive"], self._smooth)
        gain = _interp(self.mapping.get("gain", DEFAULT_MAPPING["gain"]), self._smooth)
        if (
            self._sent_cutoff is not None
            and abs(cutoff - self._sent_cutoff) < _CUTOFF_SEND_EPS
            and self._sent_drive is not None
            and abs(drive - self._sent_drive) < _DRIVE_SEND_EPS
            and self._sent_gain is not None
            and abs(gain - self._sent_gain) < _GAIN_SEND_EPS
        ):
            return

        self._sent_cutoff = cutoff
        self._sent_drive = drive
        self._sent_gain = gain
        params: dict[str, float] = {}
        if "cutoff" in self.mapping:
            params["cutoff"] = cutoff
        if "drive" in self.mapping:
            params["drive"] = drive
        if "gain" in self.mapping or "gain" in DEFAULT_MAPPING:
            params["lofiGain"] = gain
        if params:
            self.osc.set_node(self.master_node, **params)

    def set_volume(self, volume: float) -> None:
        self.master_volume = max(0.0, min(1.0, volume))
        self.osc.set_node(self.master_node, amp=self.master_volume)
