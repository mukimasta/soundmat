# Host Program

本文说明主机程序（Python 包 `soundmat/`）当前的工程实现：怎样运行、模块落在哪些文件、线程怎样分工、配置怎样读取，以及几处需要知道的实现约定。模块职责见 `ARCHITECTURE.md`，模块之间的数据契约见 `system_design/DATA_MODEL.md`，控制接口协议见 `CONTROL_API.md`，控制台见 `CONSOLE_APP.md`。

## 运行

```bash
uv sync                         # 安装 Python 3.12 与依赖
uv run soundmat --virtual       # 用虚拟垫子运行，控制台在 http://localhost:8000
uv run pytest                   # 测试
```

`--virtual` 用虚拟垫子代替控制器；`--config` 指定其他配置文件；`--host`、`--port` 覆盖控制接口的监听地址。控制台需要先在 `console/` 下构建（`npm ci && npm run build`），构建产物由控制接口直接提供；开发控制台时用 `npm run dev`，Vite 把 `/api` 和 `/ws` 转发到 8000 端口。

## 模块与文件

| 模块 | 位置 | 当前状态 |
|---|---|---|
| 运行管理 | `soundmat/supervisor/` | 建立各模块并连接；启动、停止虚拟垫子 |
| 感知 · 垫面解读 | `soundmat/perception/interpret/` | 占用判定与去抖、每环数量、控制区压力、事件、可插拔特征 |
| 感知 · 虚拟垫子 | `soundmat/perception/virtual/` | 已实现 |
| 感知 · 区域几何 | `soundmat/perception/zones.py` | 224 区的几何描述 |
| 感知 · 标准输出 | `soundmat/perception/model.py`、`perception/__init__.py` | 压力图、垫面状态、事件、快照；`Perception` 负责发布 |
| 时钟 | `soundmat/clock/` | 系统时间 |
| 状态中心 | `soundmat/store/` | 状态树、按路径修改、变化通知（尚无持久化） |
| 控制接口 | `soundmat/control/` | FastAPI：WebSocket 推送、虚拟垫子命令、提供控制台 |
| 配置 | `soundmat/config.py` + `config/soundmat.toml` | 已实现 |
| 线程间容器 | `soundmat/exchange.py` | `Latest`、`EventQueue`、`EventHub` |

垫面信号、设备连接、声音化、声音引擎、灯光引擎、录制、系统监测尚未实现。

## 线程与数据交换

每种节奏一个线程，控制接口运行在 uvicorn 的 asyncio 事件循环里（主线程）。线程之间只通过 `exchange.py` 的容器交换数据：`Latest` 保存最新值，带版本号，读的一方据此判断有没有新值；`EventHub` 为每个订阅者维护一个 `EventQueue`，订阅者每次取走积累的全部事件，所以多个使用者（声音化、录制）互不影响，事件不会丢失。

当前的线程：

1. **虚拟垫子**（`virtual-mat`）：每秒 60 次产生压力图，在本线程里调用 `Perception.feed` 完成垫面解读，发布快照和事件。以后真机上由设备连接的读取线程调用同一个入口。
2. **主线程**：uvicorn 与控制接口。

状态中心的订阅回调在修改者的线程里执行；控制接口在回调里只用 `loop.call_soon_threadsafe` 把变化交给事件循环，再由每个 WebSocket 连接自己的推送任务发出。

## 配置

`config/soundmat.toml` 在启动时读取一次。压力相关数值在文件里是 ADC 原始读数（满量程 4095），`MatConfig` 换算成归一化压力（读数 / 4095）。文件里出现未知的段或键时启动报错，避免拼错的键被悄悄忽略、装置带着默认值运行。控制台"配置 · 只读"一栏的文字由 `Config.describe()` 生成。

## 区域几何的约定

区域角度沿用第一版的逻辑坐标，因为扇区偏移 4 和灯带偏移 101 都是在这个约定下校准的（见 `DECISION.md` 第 7 条）：外环第 j 区的中心在 j × 11.25°；内环第 j 区就是第一版的第 2j+1 扇区，中心在 (2j+1) × 11.25°。区域的全局序号从第 0 环第 0 区开始依次递增（第 0 环 0–15，第 1 环 16–31，第 2 环从 32 开始，每环 32 个），标识写作"环:环内序号"，例如 `3:7`。

半径取自控制台设计稿的绘图尺寸：环中心半径从 4.0 到 25.75，环宽 2.75，灯环半径 29.15。`Zone.radius` 是除以第 7 环外缘半径后的归一化半径，给空间化使用。

## 去抖的实现

去抖按压力图到达的时刻计算：每个区记住"读数开始与当前状态不同"的时刻，持续达到 `occupy_hold`（放下）或 `release_hold`（拿起）才翻转状态并产生事件，事件时刻是确认的那一帧的时刻。中途读数回到原状态，计时清零。没有新压力图时状态不变，所以控制器断线不会让石头"被拿起"。当前初值是放下 40 ms、拿起 80 ms，尚未在真机上调过（见 `TODO.md`）。

虚拟垫子同样经过去抖。它像控制器一样持续产生压力图，所以点击之后约 40 ms 才出现"放下"，与真机一致。虚拟石头的压力固定为 0.5（约等于读数 2048）。
