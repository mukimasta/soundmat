"""全局常量集中地。无逻辑。

与固件 / 传感器设计文档对齐：8 环 × 32 wire slice（S 帧）；逻辑层统一 32 sector（L），
S→L 见 ``core.sensor.map``。108 颗 LED。串口 921600 ASCII 文本帧。
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
    """该环 wire 层 slice 数（恒 32）。逻辑 sector 数亦恒 32，见 ``wire_to_logical_adc``。"""
    return NUM_SLICES


# ── S → L / LED 对齐（设计文档 §13，部署可调）────────────────────────────
SECTOR_OFFSET = 4   # 逻辑 sector 相对 pre-offset 格顺时针偏几个 sector
LED_OFFSET = 101    # 物理灯带旋转（见 core.led.offset.apply_led_offset）
WIRE_SLICE_MIRROR = True  # True：wire slice 列镜像，对齐实物顺时针 ↔ 软件 CW sector

NUM_LEDS = 108
LED_AT_12_OCLOCK = 0  # LED #0 在 12 点，索引顺时针递增

# ── 串口（ESP32 <-> Pi） ────────────────────────────────────────────────
SERIAL_PORT = "auto"  # auto | /dev/cu.* (Mac) | /dev/ttyUSB* (Pi) | 显式路径
SERIAL_BAUD = 921600
SERIAL_FRAME_SENSOR = "S"  # ESP32 -> Pi 传感数据帧头
SERIAL_FRAME_LED = "L"     # Pi -> ESP32 LED 控制帧头
SERIAL_FRAME_DEBUG = "#"   # 双向调试帧头（无校验，接收方丢弃）
ADC_MAX = 4095             # 12-bit ADC

# 传感标定（部署时按真实传感器调；mock 用「高值=有压力」约定，real 硬件可能相反，见传感器原理文档）
SENSOR_THRESHOLD = 500.0   # 判定「有石头」的压力阈值（Mat 页可调）
SENSOR_INVERT = False      # True：压力越大 ADC 越低，需 (ADC_MAX - raw)
CONTROL_MIN = 1000.0         # R0/R1 压力之和 ≤ min → Lo-Fi 0（Mat 页可调）
CONTROL_MAX = 8000.0       # R0/R1 压力之和 ≥ max → Lo-Fi 1000（Mat 页可调）
CONTROL_SUM_MIN = 250.0    # R0/R1 压力之和 ≥ 此值 → 控制石 active（开/停播，Mat 可调）
CONTROL_RELEASE_HOLD_SEC = 0.1  # 控制石消失后延时 reset，滤 ADC 闪断
SERIAL_LOST_EXIT_SEC = 3.0      # 串口断开后多少秒退出进程

# ── Jam 行为 ────────────────────────────────────────────────────────────
JAM_IDLE_PLACE_PREVIEW_VEL = 0.5   # 开始/空闲放石 preview 音量 0–1
JAM_LOOP_PLACE_PREVIEW_VEL = 0.0   # loop 中放石立刻 preview 音量 0–1；0=关
# 复音上限：同时 alive 的 melody/bass synth 数量（不含和声 pad/鼓/master）。
# 超过则 free 最老 voice（FIFO stealing），避免密集扫描区 N 路马林巴叠满 scsynth。
# 0 = 不限制；Pi 上推荐 8–12，Mac 可设更大或 0。
JAM_MAX_MELODIC_VOICES = 12

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
# Jam 合成与 Ambient 包络均用秒/Hz；Ambient wav 经 PlayBuf+BufRateScale 自动适配 server 采样率
SAMPLE_RATE = int(os.environ.get("SOUNDMAT_SAMPLE_RATE", "44100"))

# 音频总线布局（scsynth -o 2 -i 0 时，硬件占 0-1，私有总线从 2 起，每条 stereo 占 2 通道）
OUT_BUS = 0          # 硬件立体声输出
MELODY_BUS = 2       # 旋律 + bass 总线（R2-R7）
HARMONY_BUS = 4      # 和声 pad 总线
DRUM_BUS = 6         # 鼓总线
REVERB_BUS = 8       # 混响 aux 送（ambient 用）
JAM_REVERB_BUS = 10  # Jam marimba 共享 reverb send（per-voice → 总线，省 N 倍 reverb 开销）
FIRST_PRIVATE_BUS = 12

# scsynth 内部 block size（kr UGen 步长 = 该值 / SAMPLE_RATE）。
# 默认 64 ≈ 1.45 ms，鼓 attack / 包络保留瞬态精度。**不要**为了"对齐 JACK period"
# 调大：scsynth 自己会在 callback 内跑 period/block 个 tick，省下的循环开销远小于
# DSP 总量；而 -z 4096（≈93 ms）会让所有 EnvGen.kr / Lag.kr 阶梯化，鼓含糊、
# 包络尾巴出现可听阶梯。CPU 紧张应优先靠 JAM_MAX_MELODIC_VOICES / 共享 reverb。
SC_BLOCK_SIZE = int(os.environ.get("SOUNDMAT_BLOCK_SIZE", "64"))

# ── Web 控制台 ──────────────────────────────────────────────────────────
WEB_HOST = "0.0.0.0"
WEB_PORT = 8000
