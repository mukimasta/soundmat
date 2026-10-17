"""配置：仓库里 config/soundmat.toml 的只读视图。

配置描述硬件和系统本身，启动时读取一次，运行中不变（DATA_MODEL「配置与设置」）。
压力相关数值在文件里是 ADC 原始读数，这里换算成归一化压力。
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT / "config" / "soundmat.toml"


@dataclass(frozen=True)
class MatConfig:
    full_scale: int = 4095
    occupancy_threshold_raw: float = 500.0
    occupy_hold: float = 0.04
    release_hold: float = 0.08
    sector_mirror: bool = True
    sector_offset: int = 4
    invert: bool = False

    @property
    def occupancy_threshold(self) -> float:
        """归一化的占用阈值。"""
        return self.occupancy_threshold_raw / self.full_scale

    def normalize(self, raw: float) -> float:
        """ADC 原始读数（或其总和）→ 归一化压力。"""
        return raw / self.full_scale


@dataclass(frozen=True)
class LightConfig:
    led_count: int = 108
    led_offset: int = 101
    refresh_hz: float = 60.0


@dataclass(frozen=True)
class SoundConfig:
    tick_hz: float = 60.0
    voice_budget_total: int = 48
    voice_budget_categories: dict[str, int] = field(default_factory=lambda: {"melodic": 12})
    output_latency: float = 0.03
    late_tolerance: float = 0.05
    asset_memory_mb: float = 768.0
    crossfade_seconds: float = 3.0
    expected_sample_rate: int = 48000
    expected_output_device: str = "USB"


@dataclass(frozen=True)
class SynthConfig:
    host: str = "127.0.0.1"
    port: int = 57110


@dataclass(frozen=True)
class ControlConfig:
    host: str = "0.0.0.0"
    port: int = 8000


@dataclass(frozen=True)
class Config:
    mat: MatConfig = field(default_factory=MatConfig)
    light: LightConfig = field(default_factory=LightConfig)
    sound: SoundConfig = field(default_factory=SoundConfig)
    synth: SynthConfig = field(default_factory=SynthConfig)
    control: ControlConfig = field(default_factory=ControlConfig)

    def describe(self) -> list[dict[str, str]]:
        """控制台「配置 · 只读」一栏显示的条目。"""
        m, l, s = self.mat, self.light, self.sound
        cats = "，".join(f"{k} {v}" for k, v in s.voice_budget_categories.items())
        return [
            {"label": "扇区镜像", "value": "开" if m.sector_mirror else "关"},
            {"label": "整体旋转偏移", "value": f"{m.sector_offset} 个扇区"},
            {"label": "占用阈值", "value": f"{m.occupancy_threshold_raw:g} / {m.full_scale}"},
            {"label": "去抖时间", "value": f"放下 {m.occupy_hold * 1000:g} ms · 拿起 {m.release_hold * 1000:g} ms"},
            {"label": "灯珠数量", "value": str(l.led_count)},
            {"label": "灯带对齐偏移", "value": str(l.led_offset)},
            {"label": "灯光刷新", "value": f"{l.refresh_hz:g} 次/秒"},
            {"label": "期望输出设备", "value": s.expected_output_device},
            {"label": "期望采样率", "value": f"{s.expected_sample_rate / 1000:g} kHz"},
            {"label": "声部预算", "value": f"{s.voice_budget_total}" + (f"（{cats}）" if cats else "")},
            {"label": "声音化节拍", "value": f"{s.tick_hz:g} 次/秒"},
        ]


def load_config(path: Path | str | None = None) -> Config:
    """读取配置文件；缺少的项使用默认值，多余的项报错，避免拼错的键被悄悄忽略。"""
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    with open(p, "rb") as f:
        raw = tomllib.load(f)

    def take(section: str, mapping: dict[str, str]) -> dict:
        data = dict(raw.get(section, {}))
        out = {}
        for key, attr in mapping.items():
            if key in data:
                out[attr] = data.pop(key)
        if data:
            raise ValueError(f"配置 [{section}] 有未知的项：{', '.join(sorted(data))}")
        return out

    mat = take("mat", {
        "full_scale": "full_scale",
        "occupancy_threshold": "occupancy_threshold_raw",
        "occupy_hold": "occupy_hold",
        "release_hold": "release_hold",
        "sector_mirror": "sector_mirror",
        "sector_offset": "sector_offset",
        "invert": "invert",
    })
    light = take("light", {k: k for k in ("led_count", "led_offset", "refresh_hz")})
    sound = take("sound", {k: k for k in (
        "tick_hz", "voice_budget_total", "voice_budget_categories", "output_latency",
        "late_tolerance", "asset_memory_mb", "crossfade_seconds",
        "expected_sample_rate", "expected_output_device",
    )})
    synth = take("synth", {"host": "host", "port": "port"})
    control = take("control", {"host": "host", "port": "port"})
    unknown = set(raw) - {"mat", "light", "sound", "synth", "control"}
    if unknown:
        raise ValueError(f"配置有未知的段：{', '.join(sorted(unknown))}")
    return Config(
        mat=MatConfig(**mat),
        light=LightConfig(**light),
        sound=SoundConfig(**sound),
        synth=SynthConfig(**synth),
        control=ControlConfig(**control),
    )
