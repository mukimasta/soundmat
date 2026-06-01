# SoundMat 上位机软件

公共艺术装置：圆形压力垫上放石头 → 实时生成音乐。运行在树莓派 + SuperCollider。

```
ESP32 --串口 S 帧--> Pi (Python 逻辑) --OSC--> scsynth --USB DAC--> 音响
                          └--串口 L 帧--> ESP32 --> WS2812B LED 灯带
```

## 两种模式

- **Jam**（本期重点）：节拍驱动的 Lo-Fi 循环。旋转扫描线触发旋律/bass，和声 pad
  与鼓固定循环。中心 R0/R1 控制开始/停止 + 全局 Lo-Fi 强度。
- **Ambient**：《京都岚山》氛围环境音乐（从 `sonification` 仓库迁移，素材待补，半成品）。

运行时只有一个模式 active，通过 Web 控制台切换，scsynth 常驻不重启。

## 架构

```
soundmat/
├── core/        共享 I/O：scsynth 进程、OSC、传感器读取、LED 输出
├── modes/       ModeApp 协议
├── jam/         Jam 模式（配置→理论→调度→事件→桥→SC，五层）
├── ambient/     Ambient 模式（迁移自 sonification）
└── web/         FastAPI 控制台（切换模式、调参、热力图、事件流）
sc/              SuperCollider 端：SynthDef 源码 + 编译产物
manifest/        场景声明式配置（jam/ + ambient/）
```

Jam 模式遵循「内容 (What) 与执行 (How) 彻底分离」：BPM、调性、和弦进行、旋律表、
鼓 pattern、ring 配置全部是 `manifest/jam/` 下的 YAML/TOML 数据，换曲子不动代码。

## 开发

```bash
uv sync                                  # 安装依赖
sclang sc/compile.scd                    # 编译 SynthDef -> sc/compiled/*.scsyndef
uv run soundmat                          # 启动（默认 jam/lofi_1）
uv run soundmat manifest/jam/lofi_1.toml # 指定 manifest
```

无硬件离线开发：用 `core/sensor/mock_reader.py` 回放录制数据，见 `scripts/replay_test.py`。

详见 `docs/SoundMat 软件设计与开发.md` 与 `docs/...交互与声音化设计.md`。
