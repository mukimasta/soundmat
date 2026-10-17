# Control API

控制接口（`soundmat/control/`）是控制台与主机程序之间唯一的通道。状态走一条 WebSocket，命令和设置修改走 HTTP，消息体都是 JSON。实现用 FastAPI 和 uvicorn（WebSocket 后端 wsproto），默认监听 8000 端口；同一个端口也提供构建好的控制台静态文件。

## WebSocket `/ws`

连接建立后服务端先发一条 `hello`，之后持续推送；客户端不通过 WebSocket 发命令。

| 消息 | 内容 | 时机 |
|---|---|---|
| `hello` | `geometry`（224 个区域的几何：`index`、`id`、`ring`、`slot`、`center`、`span`、`rInner`、`rOuter`）、`config`（只读配置的显示条目 `{label, value}`）、`ledCount`、`state`（状态中心的完整快照） | 连接时一次 |
| `patch` | `changes`：`[[路径, 新值], ...]`，路径是状态树里的点号路径 | 状态中心有变化时，按 30 次/秒合批 |
| `leds` | `colors`：每个逻辑灯位一个 `[r, g, b]`（0–255），不亮为 `null`；逻辑位置 0 在 12 点方向，未施加灯带偏移 | 最多 30 次/秒，有变化时 |
| `mat` | `t`、`source`（`controller` 或 `virtual`）、`pressure`（224 个整数，压力 × 1000）、`occupied`（有石头的区域序号）、`ringCounts`、`control`（控制区压力，未声明为 `null`） | 垫面变化时，最多 30 次/秒 |

客户端把 `patch` 逐条应用到 `hello` 给出的状态树上。断开后客户端丢弃全部实时数据，重连后重新收到 `hello`。

## 状态树

状态中心的树分为 `status`（运行状态，由各模块写入）、`settings`（持久设置，结构见下）和 `catalog`（可用的编排）。当前已有的路径：

| 路径 | 含义 |
|---|---|
| `status.current.virtual` | 是否使用虚拟垫子 |
| `status.current.arrangement`、`status.current.mode` | 当前编排标识与模式名 |
| `status.current.modeStatus` | 模式状态 `{text, reading, transport}` |
| `status.current.switching` | 切换中为 `{from, to, progress}`，否则 `null` |
| `status.audio.engine` | 声音引擎：在响声部数 `voices`、预算 `budget`、各类别在响数 `categories`、让位 `yields`、放弃 `rejected`、迟到 `late`、去重 `duplicates`、合成器服务重启 `restarts` |
| `status.log` | 最近的警告和错误：`[{at, level, text, count?}]`，最新在前 |
| `status.audio.assets` | `missing`（当前编排缺失的素材）、`needed`（引用总数）、`state`（`loaded`、`memoryMB`、`budgetMB`、`library`） |
| `status.mat` | 控制器链路：`connected`、`port`、`fps`（实测传感帧率）、`checksumErrors`、`problem`（问题说明）、`source`（`controller` 或 `virtual`；虚拟垫子时其余项为 `null`） |
| `catalog.arrangements` | `[{id, title, mode, modeLabel, description, ringLabels, missing, error}]` |
| `settings.sound.layout` | 音箱布局 `{azimuths, names}` |
| `settings.sound.orientation` | 垫面朝向偏移（度，0–360） |
| `settings.sound.volume` | 总音量 0–1 |
| `settings.run.defaultArrangement`、`settings.run.soundLibrary` | 默认编排、声音素材库位置 |
| `settings.recording.path`、`settings.recording.stems` | 录音保存位置、是否录制分轨 |

## HTTP

| 方法与路径 | 请求体 | 作用 |
|---|---|---|
| `GET /api/state` | — | 状态中心的完整快照 |
| `GET /api/geometry` | — | 区域几何 |
| `POST /api/virtual/toggle` | `{"zone": 序号}` | 切换一个区的虚拟石头，返回 `{"zone", "stone"}`；不在虚拟垫子模式时返回 409，序号越界返回 422 |
| `POST /api/virtual/clear` | — | 清空虚拟垫子 |
| `POST /api/arrangements/{id}/play` | — | 切换到这份编排；加载失败返回 422 和原因 |
| `POST /api/settings` | `{"changes": {"sound.volume": 0.7, ...}}` | 修改设置（键是 `settings` 下的路径；`sound.layout` 也可以是预设名 `stereo` / `quad` / `octo`）；任一项非法返回 422，整批不生效 |
