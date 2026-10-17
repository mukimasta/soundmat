# SoundMat 主机系统

SoundMat 是一件公共艺术装置：在圆形压力垫上放下石头，装置实时生成声音和灯光。本仓库是运行在树莓派上的主机程序、网页控制台，以及树莓派的系统配置与部署说明。

> 已按 `docs/ARCHITECTURE.md` 的新架构重写，进度见 `docs/DEVLOG.md`。第一版（2026 年 6 月）保存在 git 标签 `v1-ece546`。

## 快速开始（开发机，无需硬件）

需要 uv、Node.js 18 以上和 SuperCollider（macOS 装在 `/Applications/SuperCollider.app` 即可，脚本会自己找到 `sclang` 和 `scsynth`）。以下步骤在 macOS 上照做即可，Linux 相同。

```bash
uv sync
(cd console && npm ci && npm run build)
uv run python scripts/compile_instruments.py   # 编译音色，应显示"共 66 个 SynthDef 文件"
```

另开一个终端启动合成器服务，并让它一直运行：

```bash
scripts/scsynth-dev.sh                         # 立体声，CoreAudio 的默认输出设备，48 kHz
```

看到 `SuperCollider 3 server ready.` 后，在原来的终端启动主机程序：

```bash
SOUNDMAT_SOUND=/path/to/sound uv run soundmat --virtual
```

打开 http://localhost:8000 ，点垫面放石头、再点拿起；看板上"声音"应为正常（缺少素材时为需要注意），采样率 48 kHz、声道 2；音色与素材一栏显示加载情况。Mac 上没有 JACK 和 USB 声卡检查，输出设备和缓冲两栏显示"—"属正常。

1. 声音素材不在仓库里。`SOUNDMAT_SOUND` 指向包含 `samples/` 的文件夹；不设时使用与仓库并列的 `sound/`。缺少素材时照常运行，用到它的声部不发声，编排面板和看板会列出缺了哪些。
2. scsynth 报采样率错误时，在"音频 MIDI 设置"里把输出设备设为 48000 Hz 再启动。SuperCollider IDE 里如果已经启动了服务器，先关掉它，否则 57110 端口被占用。
3. 只有两个声道的设备上保持"立体声"布局；四声道、八声道布局需要多声道声卡，并用 `scripts/scsynth-dev.sh 4`（或 8）启动。
4. 不需要发声时用 `uv run soundmat --virtual --no-synth`，不必编译音色和启动 scsynth；声音引擎只记录指令，录制只产生会话数据。
5. 设置文件和录音在仓库的 `data/` 下。之前的版本会把声音素材库的位置写死在 `data/settings.json` 里，如果 `SOUNDMAT_SOUND` 不起作用，删掉这个文件即可。

测试：`uv run pytest`（连得上 scsynth 时额外运行两个真实发声的测试，否则跳过），以及 `cd console && npm test`。

## 文档

- `docs/OVERVIEW.md`：项目是什么、交付什么
- `docs/ARCHITECTURE.md`：整个系统的结构
- `docs/design/`、`docs/system_design/`、`docs/implementation/`：设计链
- `docs/implementation/HOST_PROGRAM.md`：主机程序的工程实现与运行方式
- `docs/implementation/DEPLOYMENT.md`：树莓派部署
- `AGENTS.md`：Agent 工作协议
