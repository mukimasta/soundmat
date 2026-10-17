# Synth

本文说明合成器服务（scsynth）这一侧的工程实现：音色怎样编写和编译，主机程序怎样在 scsynth 里搭建混音结构、发出带时间戳的指令、发现 scsynth 重启。声音引擎的系统机制见 `system_design/SOUND_ENGINE.md`，Python 侧的引擎实现见 `HOST_PROGRAM.md`。

## 运行 scsynth

scsynth 是独立的系统服务，主机程序不启动它，只通过 UDP 57110 端口通信（配置 `[synth]`）。树莓派上由 systemd 服务启动（JACK 之后，见 `DEPLOYMENT.md`）；开发机上用 `scripts/scsynth-dev.sh [声道数]` 手动启动，macOS 走 CoreAudio 的默认输出设备。scsynth 的硬件输出声道数（`-o`）不能少于音箱布局的声道数。

主机程序默认连接 scsynth；连不上时照常运行、什么都不发，等 scsynth 出现后自动接上。`--no-synth` 改用只记录指令的声音引擎。

云端和 CI 没有声卡：可以安装 `jackd2` 和 `supercollider-server`，用 `jackd -d dummy -r 48000` 起一个虚拟声卡，再启动 scsynth。`tests/test_scsynth.py` 的最后一个测试在本机能连上 scsynth 时运行真实的 Jam，否则跳过。

## 音色

音色源码在 `instruments/`，用 SuperCollider 语言编写：

| 目录 | 内容 |
|---|---|
| `lib/common.scd` | 所有音色共用的约定：空间化输出 `~smOut`、持续声部的包络 `~smGateEnv`、按声道数命名 `~smDef` |
| `lib/jam_common.scd` | 第一版 Jam 音色共用的函数（与 web 原型 Tone.js 对齐） |
| `players/` | 素材回放：单声道 / 立体声，带或不带保时长变调 |
| `ambient/` | Ambient 的合成音色（管风琴 drone、马林巴） |
| `jam/` | Jam 的和声铺底、旋律、贝斯、鼓 |
| `system/` | 混音结构：模式总处理、共用效果、总输出、测试音 |

SynthDef 的声道数在编译时固定，所以每个音色按 2、4、8 声道各编译一份，名字后缀声道数（`marimbaNote_2`）。主机程序按当前音箱布局的声道数选用。编译：`uv run python scripts/compile_instruments.py`（等价于 `sclang instruments/build.scd`），产物在 `instruments/compiled/`，不进仓库，部署时随程序同步。树莓派上不需要 sclang。脚本按 `SOUNDMAT_SCLANG`、`PATH`、`/Applications/SuperCollider.app/Contents/MacOS/sclang` 的顺序找 sclang；只在 Linux 上默认设置 `QT_QPA_PLATFORM=offscreen`（无桌面也能运行），macOS 版 SuperCollider.app 只带 cocoa 平台插件，不能设置 offscreen。

### 音色的约定

1. 音色把信号交给 `~smOut.(干声, 效果发送)`。单声道信号按增益 `g0`…`g{N−1}` 分配到各只音箱；立体声信号左声道按 `gl*`、右声道按 `gr*` 分配。增益带 50 ms 平滑。干声写到 `out`（声部所在的总线），效果发送写到 `fx`（共用效果的发送总线）。
2. 持续声部用 `~smGateEnv`：`atk` 淡入、`gate` 置 0 时按 `rel` 淡出并释放。单次声音自己结束（`doneAction: 2`）。
3. 素材回放的参数：`buf`、`loop`（持续 1、单次 0）、`amp`（dB）、`rate`、`rateVar`、`lpf`、`hpf`、`revSend`，变调版多 `semitones`、`winSize`。主机程序按素材的声道数和是否有 `semitones` 选择 `sm_play_mono` / `sm_play_stereo` / `…_tune`。
4. 不认识的参数会被 scsynth 忽略，所以编排可以随意给音色加参数，只要音色里有同名控制。

第一版音色的改动：输出从固定的立体声改为多声道空间化；和声铺底从"保持 hold 秒后自己结束"改为持续声部（和弦层靠 gate 释放，`rel` 1.5 秒），因为新版的和声是带开始时刻的持续声部；`pan`、`Balance2` 去掉，方位由空间化决定。

## 节点树与总线

```text
根（0）
├── 组 100：模式实例
│   ├── 实例组（每个模式实例一个，切换编排时新旧两个并存）
│   │   ├── 声部……（加在组头）
│   │   ├── 共用效果（sm_fx_freeverb 或 sm_fx_jam）：读效果发送总线 → 写效果返回总线
│   │   └── 模式总处理（sm_mode）：各总线 × 增益 + 效果返回 → Lo-Fi → 交叉淡化增益 → 总输出总线
│   └── ……
└── 组 101：总输出（sm_master）：系统音量 → 限幅（−1 dB）→ 硬件输出 0…N−1
```

每个模式实例分配：模式声明的每条总线（最多 12 条）、效果发送总线、效果返回总线，各 N 个声道；全局还有总输出总线和一条从不写入的静音总线（`sm_mode` 未用的输入指向它）。私有总线从 128 号开始（假设硬件输入输出合计不超过 128 个声道），用首次适应分配，释放推迟 1 秒，避免还在淡出的节点写到被重新分配的总线上。主机程序分配的节点号从 1999999999 往下递减，与引擎分配的声部号（从 1000 往上）不会相遇。

全局参数里，`bus.<总线>` 设置该总线在 `sm_mode` 里的增益，`fx.<参数>` 设置共用效果，其余（`cutoff`、`drive`、`lofiGain`）交给 `sm_mode`。`cutoff` 达到 18 kHz（默认 20 kHz）时低通被旁路：低通截止接近奈奎斯特频率时会失稳，第一版也把上限定在 18 kHz。

## 时间戳

引擎每一拍发出的指令先按执行时刻分组暂存，一拍结束时整批发出：同一时刻的指令放进一个 OSC bundle（超过 8 KB 拆成几个）。时刻是系统时间（单调时钟），发送时换算为墙钟时间 `time.time() + (时刻 − time.monotonic())` 作为 bundle 时间戳；每次发送都现算，开机后 NTP 校时让墙钟跳变也不受影响。主机程序与 scsynth 在同一台机器上，共用系统时钟。时刻已到的指令用"立即执行"的时间戳，scsynth 不会为它们记录迟到警告。

## 连接、重启与通知

主机程序每 0.5 秒发一次 `/status`，并在已连接时用 `/n_query 100` 确认根组还在。

1. 第一次收到 `/status.reply`：发 `/notify 1` 订阅节点结束通知，`/d_loadDir` 加载编译好的音色；收到 `/done /d_loadDir` 后用 `/g_freeAll 0` 清空整棵节点树（主机程序重启时 scsynth 照常运行，上一次的节点还在），再建立组 100、101，报告"重新启动过"。引擎据此重建混音结构、重新加载素材，下一拍对账恢复所有持续声部。
2. `/n_query` 回答"找不到节点"：scsynth 在两次查询之间重启过，按第 1 步重新接上。
3. 超过 2 秒没有回答：视为离线，不再发送任何指令，等它回来后按第 1 步接上。
4. `/n_end` 通知某个声部结束：如果是引擎的声部，转告引擎移出声部表。

素材用 `/b_allocRead` 读入缓冲区；用到缺失素材的声部不发送，并立即当作结束告诉引擎。

## 电平

`sm_mode` 对每条输入总线、`sm_master` 对总输出，用 `SendPeakRMS` 以 10 次/秒回报峰值（`/sm_peak`）。主机程序把总输出各声道和每环的峰值整理成控制台的 `levels` 消息：每环分左右两侧，左侧取方位在 180°–360° 的音箱、右侧取 0°–180° 的音箱（正前和正后两侧都算），超过 1 秒没有更新的值不算。

## 录制

`sm_mode` 除了把各输入相加，还把每条输入（乘过总线增益和交叉淡化增益）加到一条按总线名分配的全局分轨总线上，效果返回加到全局的 `fx` 分轨总线；未用的输入指向一条废弃总线。所以分轨与模式实例无关，录制中切换编排时新旧两组一起汇入，录音不中断。

开始录制时，每个文件分配一个缓冲区（`/b_alloc` 65536 帧 × N 声道），用 `/b_write … "wav" 格式 0 0 1` 以流式写入的方式打开，再在稍后的时刻于组 101 末尾启动 `sm_rec`（`DiskOut`）：总输出从硬件输出总线读取，分轨从全局分轨总线读取。异步命令按顺序执行，所以分配、打开、开始的次序是保证的。停止时在同一个 bundle 里依次释放录制节点、`/b_close`、`/b_free`。打板提示音 `sm_slate` 在组 101 的开头、按时间戳播放，写到总输出总线，经过系统音量送到音箱，也进入总输出录音。
