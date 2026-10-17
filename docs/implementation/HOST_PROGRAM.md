# Host Program

本文说明主机程序（Python 包 `soundmat/`）当前的工程实现：怎样运行、模块落在哪些文件、线程怎样分工、配置怎样读取，以及几处需要知道的实现约定。模块职责见 `ARCHITECTURE.md`，模块之间的数据契约见 `system_design/DATA_MODEL.md`，控制接口协议见 `CONTROL_API.md`，控制台见 `CONSOLE_APP.md`。

## 运行

```bash
uv sync                         # 安装 Python 3.12 与依赖
uv run soundmat --virtual       # 用虚拟垫子运行，控制台在 http://localhost:8000
uv run pytest                   # 测试
```

`--virtual` 用虚拟垫子代替控制器；`--config` 指定其他配置文件；`--data-dir` 指定本机数据目录（设置文件 `settings.json` 和录音，默认是程序目录下的 `data/`，树莓派上是 `/home/soundmat/data`）；`--host`、`--port` 覆盖控制接口的监听地址。控制台需要先在 `console/` 下构建（`npm ci && npm run build`），构建产物由控制接口直接提供；开发控制台时用 `npm run dev`，Vite 把 `/api` 和 `/ws` 转发到 8000 端口。

## 模块与文件

| 模块 | 位置 | 当前状态 |
|---|---|---|
| 运行管理 | `soundmat/supervisor/` | 建立各模块并连接；启动与停止；切换编排（加载失败保持当前编排） |
| 感知 · 垫面解读 | `soundmat/perception/interpret/` | 占用判定与去抖、每环数量、控制区压力、事件、可插拔特征 |
| 感知 · 虚拟垫子 | `soundmat/perception/virtual/` | 已实现 |
| 感知 · 区域几何 | `soundmat/perception/zones.py` | 224 区的几何描述 |
| 感知 · 标准输出 | `soundmat/perception/model.py`、`perception/__init__.py` | 压力图、垫面状态、事件、快照；`Perception` 负责发布 |
| 时钟 | `soundmat/clock/` | 系统时间；`BeatClock` 固定节拍线程 |
| 声音化 · 意图 | `soundmat/sonification/intent.py` | 持续声部、定时事件、全局参数、灯光层、模式状态 |
| 声音化 · 模式框架 | `soundmat/sonification/mode.py`、`sonification/__init__.py` | 模式生命周期、编排头部、每拍调度、交叉淡化切换、出错时保持上一拍 |
| 声音引擎 | `soundmat/sound/engine.py` | 对账、声部预算、定时与去重、混音结构与交叉淡化、重启后重建 |
| 声音引擎 · 空间化 | `soundmat/sound/spatial.py` | 音箱布局预设与分配公式 |
| 声音引擎 · 合成器接口 | `soundmat/sound/backend.py` | 抽象指令接口；`RecordingBackend` 只记录指令 |
| 系统监测 · 日志 | `soundmat/monitor/log.py` | 最近的警告和错误 |
| 声音化 · 编排文件 | `soundmat/sonification/arrangements.py` + `arrangements/` | 读取与校验，格式见 `ARRANGEMENTS.md` |
| 声音化 · Ambient | `soundmat/sonification/ambient/` | 持续 / 间歇 / 触发、分档、条件、位置策略、灯光 |
| 声音化 · 灯光工具 | `soundmat/sonification/lights.py` | 逐像素绘制灯光层 |
| 声音化 · Jam | `soundmat/sonification/jam/` | 走带、Lo-Fi、和声 / 鼓 / 扫描命中的精确时刻、预听、灯光；理论与时间方案移植自第一版 |
| 声音引擎 · 素材库 | `soundmat/sound/assets.py` | 读文件头估算内存、预算检查、引用计数、重启后重载 |
| 状态中心 · 设置 | `soundmat/store/settings.py` | 默认值、校验、原子写入 `settings.json` |
| 状态中心 | `soundmat/store/` | 状态树、按路径修改、变化通知（尚无持久化） |
| 控制接口 | `soundmat/control/` | FastAPI：WebSocket 推送、虚拟垫子命令、提供控制台 |
| 配置 | `soundmat/config.py` + `config/soundmat.toml` | 已实现 |
| 线程间容器 | `soundmat/exchange.py` | `Latest`、`EventQueue`、`EventHub` |

垫面信号、设备连接、scsynth 实现、灯光引擎、录制、系统监测的其余部分尚未实现。没有 scsynth 实现之前，主机程序总是使用 `RecordingBackend`，不发声。

## 线程与数据交换

每种节奏一个线程，控制接口运行在 uvicorn 的 asyncio 事件循环里（主线程）。线程之间只通过 `exchange.py` 的容器交换数据：`Latest` 保存最新值，带版本号，读的一方据此判断有没有新值；`EventHub` 为每个订阅者维护一个 `EventQueue`，订阅者每次取走积累的全部事件，所以多个使用者（声音化、录制）互不影响，事件不会丢失。

当前的线程：

1. **虚拟垫子**（`virtual-mat`）：每秒 60 次产生压力图，在本线程里调用 `Perception.feed` 完成垫面解读，发布快照和事件。以后真机上由设备连接的读取线程调用同一个入口。
2. **声音化**（`sonification`）：`BeatClock` 每秒 60 拍（配置 `sound.tick_hz`）。每拍取走垫面事件、读取最新快照、调用所有模式实例（切换期间新旧两个），把声音意图交给声音引擎，再处理合成器服务的通知、释放淡出完毕的实例。声音引擎不是线程安全的，只在这个线程里调用；切换编排的请求从其他线程放进队列，在下一拍开始时执行。某一拍的计算超过节拍间隔时不补拍，直接跳到当前时刻，并计入 `BeatClock.overruns`。
3. **主线程**：uvicorn 与控制接口。

状态中心的订阅回调在修改者的线程里执行；控制接口在回调里只用 `loop.call_soon_threadsafe` 把变化交给事件循环，再由每个 WebSocket 连接自己的推送任务发出。

## 配置

`config/soundmat.toml` 在启动时读取一次。压力相关数值在文件里是 ADC 原始读数（满量程 4095），`MatConfig` 换算成归一化压力（读数 / 4095）。文件里出现未知的段或键时启动报错，避免拼错的键被悄悄忽略、装置带着默认值运行。控制台"配置 · 只读"一栏的文字由 `Config.describe()` 生成。

## 区域几何的约定

区域角度沿用第一版的逻辑坐标，因为扇区偏移 4 和灯带偏移 101 都是在这个约定下校准的（见 `DECISION.md` 第 7 条）：外环第 j 区的中心在 j × 11.25°；内环第 j 区就是第一版的第 2j+1 扇区，中心在 (2j+1) × 11.25°。区域的全局序号从第 0 环第 0 区开始依次递增（第 0 环 0–15，第 1 环 16–31，第 2 环从 32 开始，每环 32 个），标识写作"环:环内序号"，例如 `3:7`。

半径取自控制台设计稿的绘图尺寸：环中心半径从 4.0 到 25.75，环宽 2.75，灯环半径 29.15。`Zone.radius` 是除以第 7 环外缘半径后的归一化半径，给空间化使用。

## 去抖的实现

去抖按压力图到达的时刻计算：每个区记住"读数开始与当前状态不同"的时刻，持续达到 `occupy_hold`（放下）或 `release_hold`（拿起）才翻转状态并产生事件，事件时刻是确认的那一帧的时刻。中途读数回到原状态，计时清零。没有新压力图时状态不变，所以控制器断线不会让石头"被拿起"。当前初值是放下 40 ms、拿起 80 ms，尚未在真机上调过（见 `TODO.md`）。

虚拟垫子同样经过去抖。它像控制器一样持续产生压力图，所以点击之后约 40 ms 才出现"放下"，与真机一致。虚拟石头的压力固定为 0.5（约等于读数 2048）。

## 声音引擎的实现

引擎通过 `sound/backend.py` 的 `Backend` 接口发出抽象指令：建立和释放一个模式实例的混音结构、设置它的交叉淡化增益和全局参数、开始/修改/淡出/强制释放一个声部、加载和释放素材、设置总输出。声部编号由引擎从 1000 开始分配，正好可以直接用作 scsynth 的节点号。每条指令都带执行时刻：意图里的时刻加上配置的输出延迟 `sound.output_latency`（30 ms）；定时事件晚于 `sound.late_tolerance`（50 ms）就丢弃。

`RecordingBackend` 是不发声的实现：照单记录指令，并模拟合成器服务的通知——淡出的声部在淡出时长之后结束，单次声音在固定的 2 秒后结束，`simulate_restart()` 模拟合成器服务重启。测试用它检查对账和调度的结果。

已发出的定时事件标识保留 30 秒用于去重。合成器服务重启后引擎调用 `rebuild`：清空声部表，重新设置总输出、建立各实例的混音结构、恢复全局参数，并调用 `on_rebuild` 回调（例如素材库重新加载素材）；下一拍的对账把所有持续声部重新开始。

空间化公式见 `sound/spatial.py` 的说明：方向上在相邻两只音箱之间等功率分配，再按半径与均匀分布混合，最后归一到等功率。预设布局有立体声（左 330°、右 30°）、四声道（左前 315°、右前 45°、右后 135°、左后 225°）和八声道（0° 起每 45°）。

## 设置与启动

设置保存在数据目录的 `settings.json`，结构与状态树的 `settings` 一致，但只写入改过的项：没改过的项每次启动时取默认值，声音素材库的默认位置因此跟随环境变量 `SOUNDMAT_SOUND` 和程序目录。读取时逐项校验，非法或无法读取的项回到默认值并写一条警告；修改经过 `Settings.update` 逐项校验，任何一项非法就整批拒绝。写入先写同目录的临时文件、`fsync` 后再 `os.replace`，断电时要么是旧文件、要么是新文件。

声音相关的设置（总音量、音箱布局、朝向）变化时，运行管理把应用动作放进声音化的命令队列，在下一拍由节拍线程交给声音引擎。素材库位置变化时重新检查所有编排的素材。启动时播放设置里的默认编排；它不存在时改用第一份能找到的编排，并写一条警告。
