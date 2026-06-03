# SoundMat 部署指南

```
ESP32 ──S 帧──► 上位机 (Python) ──OSC──► scsynth ──► 音响
                    └──L 帧──► ESP32 ──► WS2812B
```

默认启动 **Jam 模式**（`manifest/jam/lofi_1.toml`）。Web 控制台：`http://<host>:8000`。

---

## 1. 通用准备

### 依赖

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/)（推荐）或 venv + pip
- SuperCollider（`scsynth` + `sclang`）
- ESP32 固件（见同级目录 `soundmat_firmware/`）

### 安装 Python 包

```bash
cd soundmat
uv sync
```

### 编译 SynthDef

```bash
sclang sc/compile.scd
# 或
uv run python scripts/compile_synths.py
```

确认产物：`ls sc/compiled/*.scsyndef`

可在 Mac 编好后把 `sc/compiled/` 拷到树莓派，Pi 上不必再编。

---

## 2. 环境变量

| 变量 | 用途 | Mac 默认 | 树莓派示例 |
| --- | --- | --- | --- |
| `SOUNDMAT_SCSYNTH` | 运行时启动的 scsynth | `/Applications/SuperCollider.app/Contents/Resources/scsynth` | `/usr/bin/scsynth` |
| `SOUNDMAT_SCLANG` | 编译 SynthDef 的 sclang | `/Applications/.../MacOS/sclang` | `/usr/bin/sclang` |
| `SOUNDMAT_SAMPLE_RATE` | scsynth `-S` 采样率 | `44100` | `44100` 或 DAC 支持的值 |
| `SOUNDMAT_BLOCK_SIZE` | scsynth `-z` 内部 block size，决定 kr UGen 步长（鼓 attack/包络精度）。**保持 64**，不要为"对齐 JACK period"调大 | `64` | `64` |

串口**不用**环境变量：CLI `--port auto`（默认）或显式路径即可。Linux `auto` 会排除板载 `ttyS*` / `ttyAMA*`（仅 USB 口）。

**Ambient 素材：** Kyoto wav 若为 48000 Hz，**不必批量重转**。`playMono` / `playStereo` 使用 `PlayBuf` + `BufRateScale`，scsynth 会按 server 采样率正确回放音高与时长。仅 Jam 合成为实时生成，与 wav 文件采样率无关。

写入 shell 配置（Pi 示例）：

```bash
export SOUNDMAT_SCSYNTH=/usr/bin/scsynth
export SOUNDMAT_SCLANG=/usr/bin/sclang
```

---

## 3. macOS 开发机

### 安装 SuperCollider

从 [supercollider.github.io](https://supercollider.github.io/download) 安装 `.app`，默认路径已被 `config.py` 识别；自定义安装位置时设 `SOUNDMAT_SCSYNTH` / `SOUNDMAT_SCLANG`。

### 启动

```bash
uv sync
sclang sc/compile.scd          # 首次或改 SynthDef 后
uv run soundmat --list-ports   # 查看 ESP32 串口
uv run soundmat                # 默认 Jam + auto 串口
```

常用参数：

```bash
uv run soundmat --port /dev/cu.usbserial-XXXX   # 显式串口
uv run soundmat --mock                          # 无硬件：虚拟垫 + 回放
uv run soundmat --no-sc                         # 不启音频，仅逻辑/LED
```

### 串口注意

- 使用 **`/dev/cu.*`**（call-out），不要用 `tty.*` 同时占口
- 关闭 `idf.py monitor`、`screen`、Arduino IDE 等占口程序
- 打开串口可能复位 ESP32；程序会等首帧 `S:`（最多 8s）再发 LED

---

## 4. 树莓派部署

### 系统包

```bash
sudo apt update
sudo apt install -y git supercollider
sudo usermod -aG dialout $USER   # 串口权限；登出后再登录
```

确认路径：

```bash
which scsynth sclang
```

### 代码与 SynthDef

```bash
git clone <repo> soundmat && cd soundmat
uv sync
export SOUNDMAT_SCLANG=/usr/bin/sclang
sclang sc/compile.scd
```

### 环境变量（`~/.bashrc` 或启动脚本）

```bash
export SOUNDMAT_SCSYNTH=/usr/bin/scsynth
export SOUNDMAT_SCLANG=/usr/bin/sclang
# SOUNDMAT_BLOCK_SIZE 保持默认 64，不需要 export
```

### 音频引擎（jackd）

Pi 上推荐用 JACK 跑 scsynth。`-p`（JACK period）控制延迟与 XRun 容忍度，`-z`
（scsynth block，环境变量 `SOUNDMAT_BLOCK_SIZE`）控制 kr UGen 步长——**两者解耦**，
不要绑等：

```bash
jackd -P75 -t2000 -dalsa -dhw:Audio -r44100 -p2048 -n2
# SOUNDMAT_BLOCK_SIZE 保持默认 64
```

`-p` 调参经验（@44.1 kHz）：

- `-p 1024`（23 ms 延迟）：装置感最好；50 颗石可能 XRun
- **`-p 2048`（46 ms）：推荐起步**，调度余量大、装置距离 1–2 m 听不出延迟
- `-p 4096`（93 ms）：仅在 2048 持续 XRun 时再加，敲石头到出声会有明显迟滞

`-z` 不要调大：`-z 4096` 会让 `EnvGen.kr` 步长 ≈93 ms，鼓 attack 阶梯化。CPU 紧张
请优先：(1) 降低 `JAM_MAX_MELODIC_VOICES`（Web Calibration `Max voices`，Pi 推荐 12）；
(2) 关闭 Pi 本机 Chromium / `/mat` 页；(3) 把 `-p` 加大到 4096。

### 硬件连接

1. ESP32 USB → Pi（传感 + LED 回传，921600 baud）
2. USB DAC / 3.5mm → 音响（系统默认音频输出）
3. 灯带建议独立 5V 供电（108 灯全亮峰值约 6.5A，纯 USB 可能 brownout）

### 启动

```bash
uv run soundmat --list-ports
uv run soundmat --port auto
# 或
uv run soundmat --port /dev/ttyUSB0
```

局域网访问 Web：`http://<pi-ip>:8000`

---

## 5. 上机检查

| 检查项 | 期望 |
| --- | --- |
| 终端 | `[scsynth] server ready` |
| 终端 | `[main] 等待 ESP32 就绪… ok`（超时也会继续，见下） |
| 终端 | **无** `转 mock` |
| `GET /api/status` | `"mock": false`, `"serial_ready": true` |
| Mat 热力图 | `seq` 持续增加 |
| R0/R1 放石 | 开拍、lofi 条变化 |
| R2–R7 放石 | 扫描触发旋律 |

固件 boot 约 5s 灯效动画期间不发 S 帧，8s 等待可能踩线显示「超时」——S 帧到了即正常。

---

## 6. 固件侧单独验证

仓库 `soundmat_firmware/tools/`（与上位机协议一致）：

```bash
# 仅测 S 帧 / 热力图
python3 soundmat_firmware/tools/plot_sensors.py --port auto

# 仅测 L 帧 / 灯带
python3 soundmat_firmware/tools/led_test.py --port auto --rgb 333333
```

---

## 7. Web 校准（Mat 页）

部署后可在 **Calibration** 调整（重启恢复默认）：

- **Threshold** — 压力阈值（默认 500）
- **Sector offset** — S→L 逻辑 sector 旋转（默认 4）
- **Slice mirror** — wire slice 列镜像，对齐实物顺时针与软件 CW sector（默认开；`--mock` 自动关）
- **LED offset** — 物理灯带旋转（默认 101）
- **Lo-Fi sum min/max** — R0/R1 压力之和映射到 Lo-Fi 0–1000（默认 1000 / 8000）
- **Control sum min** — R0/R1 压力之和 ≥ 此值才视为有控制石（默认 250）；闪断 100ms 内不 reset

---

## 8. 常见问题

**串口打开失败 → 自动 mock**  
终端有 `转 mock`；`/api/status` 里 `"mock": true`。关占口程序、`--list-ports` 换 `--port`。

**无声**  
查 scsynth 是否 ready、SynthDef 是否编译、系统音频输出设备、Pi 上是否设了 `SOUNDMAT_SCSYNTH`。

**有传感无灯**  
查 L 帧：`led_test.py`；USB 供电；固件是否已过 boot 进主循环。

**Ambient（Kyoto）模式**  
需要 `sc/assets/samples/kyoto/` 下 wav 样本；缺文件会启动失败。上机联调建议先用 Jam。

---

## 9. 参考

- 架构与开发：`README.md`
- ESP32 固件：`../soundmat_firmware/`
- 默认 manifest：`manifest/jam/lofi_1.toml`
