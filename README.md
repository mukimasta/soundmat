# SoundMat 主机系统

SoundMat 是一件公共艺术装置：在圆形压力垫上放下石头，装置实时生成声音和灯光。本仓库是运行在树莓派上的主机程序、网页控制台，以及树莓派的系统配置与部署说明。

> 已按 `docs/ARCHITECTURE.md` 的新架构重写，进度见 `docs/DEVLOG.md`。第一版（2026 年 6 月）保存在 git 标签 `v1-ece546`。

## 快速开始（开发机，无需硬件）

需要 uv、Node.js 和 SuperCollider。

```bash
uv sync
(cd console && npm ci && npm run build)
uv run python scripts/compile_instruments.py   # 编译音色
scripts/scsynth-dev.sh &                       # 启动合成器服务
uv run soundmat --virtual                      # 打开 http://localhost:8000 ，点垫面放石头
```

声音素材不在仓库里：程序会在 SoundMat 总文件夹的 `sound/` 里找，也可以用环境变量 `SOUNDMAT_SOUND` 指定。没有合成器服务时加 `--no-synth`，声音引擎只记录指令、不发声。

测试：`uv run pytest`，以及 `cd console && npm test`。

## 文档

- `docs/OVERVIEW.md`：项目是什么、交付什么
- `docs/ARCHITECTURE.md`：整个系统的结构
- `docs/design/`、`docs/system_design/`、`docs/implementation/`：设计链
- `docs/implementation/HOST_PROGRAM.md`：主机程序的工程实现与运行方式
- `docs/implementation/DEPLOYMENT.md`：树莓派部署
- `AGENTS.md`：Agent 工作协议
