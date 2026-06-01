"""全局常量集中地。无逻辑。

与固件 / 传感器设计文档对齐：8 环 × 32 扇区（内 2 环物理上 16 区，但固件仍发 32 值，
合并交给 Pi），108 颗 LED。串口 921600 ASCII 文本帧。
"""
from pathlib import Path

# ── 路径 ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent  # 项目根 src/soundmat/
SC_DIR = ROOT / "sc"
COMPILED_DIR = SC_DIR / "compiled"  # *.scsyndef 编译产物
ASSETS_DIR = SC_DIR / "assets"
SAMPLES_DIR = ASSETS_DIR / "samples"
MANIFEST_DIR = ROOT / "manifest"
DEFAULT_MANIFEST = MANIFEST_DIR / "jam" / "lofi_1.toml"
RECORDINGS_DIR = ROOT / "recordings"

# ── 传感器几何 ──────────────────────────────────────────────────────────
NUM_RINGS = 8       # 环形电极（R0 最内 … R7 最外）
NUM_SLICES = 32     # 射线电极（扇区）数量
INNER_RINGS = 2     # 内侧物理上只有 16 区的环数（R0,R1）
INNER_SLICES = 16
SENSOR_VALUES = NUM_RINGS * NUM_SLICES  # 256，S 帧负载长度


def slices_at(ring: int) -> int:
    """该环物理有效扇区数（内 2 环 16，其余 32）。"""
    return INNER_SLICES if ring < INNER_RINGS else NUM_SLICES


# ── LED ─────────────────────────────────────────────────────────────────
NUM_LEDS = 108
LED_AT_12_OCLOCK = 0  # LED #0 在 12 点，索引顺时针递增

# ── 串口（ESP32 <-> Pi） ────────────────────────────────────────────────
SERIAL_PORT = "/dev/ttyUSB0"
SERIAL_BAUD = 921600
SERIAL_FRAME_SENSOR = "S"  # ESP32 -> Pi 传感数据帧头
SERIAL_FRAME_LED = "L"     # Pi -> ESP32 LED 控制帧头
SERIAL_FRAME_DEBUG = "#"   # 双向调试帧头（无校验，接收方丢弃）
ADC_MAX = 4095             # 12-bit ADC

# 传感标定（部署时按真实传感器调；mock 用「高值=有压力」约定，real 硬件可能相反，见传感器原理文档）
SENSOR_THRESHOLD = 800.0   # 判定「有石头」的压力阈值
SENSOR_INVERT = False      # True：压力越大 ADC 越低，需 (ADC_MAX - raw)
CONTROL_FULL_SCALE = 12000.0  # R0/R1 压力之和达此值 → Lo-Fi 控制值 1000（封顶）

# ── SuperCollider / scsynth ─────────────────────────────────────────────
# macOS 开发机 / 树莓派部署可用环境变量 SOUNDMAT_SCSYNTH / SOUNDMAT_SCLANG 覆盖
import os

SCSYNTH_PATH = os.environ.get(
    "SOUNDMAT_SCSYNTH",
    "/Applications/SuperCollider.app/Contents/Resources/scsynth",
)
SCLANG_PATH = os.environ.get(
    "SOUNDMAT_SCLANG",
    "/Applications/SuperCollider.app/Contents/MacOS/sclang",
)
SC_HOST = "127.0.0.1"
SC_PORT = 57110
SAMPLE_RATE = 48000

# 音频总线布局（scsynth -o 2 -i 0 时，硬件占 0-1，私有总线从 2 起，每条 stereo 占 2 通道）
OUT_BUS = 0          # 硬件立体声输出
MELODY_BUS = 2       # 旋律 + bass 总线（R2-R7）
HARMONY_BUS = 4      # 和声 pad 总线
DRUM_BUS = 6         # 鼓总线
REVERB_BUS = 8       # 混响 aux 送（ambient 用）
FIRST_PRIVATE_BUS = 10

# ── Web 控制台 ──────────────────────────────────────────────────────────
WEB_HOST = "0.0.0.0"
WEB_PORT = 8000
