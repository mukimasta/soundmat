# Control API

控制接口（`soundmat/control/`）是控制台与主机程序之间唯一的通道。状态走一条 WebSocket，命令和设置修改走 HTTP，消息体都是 JSON。实现用 FastAPI 和 uvicorn（WebSocket 后端 wsproto），默认监听 8000 端口；同一个端口也提供构建好的控制台静态文件。

## WebSocket `/ws`

连接建立后服务端先发一条 `hello`，之后持续推送；客户端不通过 WebSocket 发命令。

| 消息 | 内容 | 时机 |
|---|---|---|
| `hello` | `geometry`（224 个区域的几何：`index`、`id`、`ring`、`slot`、`center`、`span`、`rInner`、`rOuter`）、`config`（只读配置的显示条目 `{label, value}`）、`ledCount`、`state`（状态中心的完整快照） | 连接时一次 |
| `patch` | `changes`：`[[路径, 新值], ...]`，路径是状态树里的点号路径 | 状态中心有变化时，按 30 次/秒合批 |
| `mat` | `t`、`source`（`controller` 或 `virtual`）、`pressure`（224 个整数，压力 × 1000）、`occupied`（有石头的区域序号）、`ringCounts`、`control`（控制区压力，未声明为 `null`） | 垫面变化时，最多 30 次/秒 |

客户端把 `patch` 逐条应用到 `hello` 给出的状态树上。断开后客户端丢弃全部实时数据，重连后重新收到 `hello`。

## 状态树

状态中心的树分为 `status`（运行状态，由各模块写入）和 `settings`（持久设置，后续阶段加入）。当前已有的路径：

| 路径 | 含义 |
|---|---|
| `status.current.virtual` | 是否使用虚拟垫子 |
| `status.current.arrangement`、`status.current.mode` | 当前编排标识与模式名 |
| `status.current.modeStatus` | 模式状态 `{text, reading, transport}` |
| `status.current.switching` | 切换中为 `{to, progress}`，否则 `null` |
| `status.audio.engine` | 声音引擎：在响声部数 `voices`、预算 `budget`、各类别在响数 `categories`、让位 `yields`、放弃 `rejected`、迟到 `late`、去重 `duplicates`、合成器服务重启 `restarts` |
| `status.log` | 最近的警告和错误：`[{at, level, text, count?}]`，最新在前 |

## HTTP

| 方法与路径 | 请求体 | 作用 |
|---|---|---|
| `GET /api/state` | — | 状态中心的完整快照 |
| `GET /api/geometry` | — | 区域几何 |
| `POST /api/virtual/toggle` | `{"zone": 序号}` | 切换一个区的虚拟石头，返回 `{"zone", "stone"}`；不在虚拟垫子模式时返回 409，序号越界返回 422 |
| `POST /api/virtual/clear` | — | 清空虚拟垫子 |
