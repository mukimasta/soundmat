# Control API

控制接口（`soundmat/control/`）是控制台与主机程序之间唯一的通道。状态走一条 WebSocket，命令和设置修改走 HTTP，消息体都是 JSON。实现用 FastAPI 和 uvicorn（WebSocket 后端 wsproto），默认监听 8000 端口；同一个端口也提供构建好的控制台静态文件。

## WebSocket `/ws`

连接建立后服务端先发一条 `hello`，之后持续推送；客户端不通过 WebSocket 发命令。

| 消息 | 内容 | 时机 |
|---|---|---|
| `hello` | `geometry`（224 个区域的几何：`index`、`id`、`ring`、`slot`、`center`、`span`、`rInner`、`rOuter`）、`config`（只读配置的显示条目 `{label, value}`）、`ledCount`、`state`（状态中心的完整快照） | 连接时一次 |
| `patch` | `changes`：`[[路径, 新值], ...]`，路径是状态树里的点号路径 | 状态中心有变化时，最多 30 次/秒合批 |
| `levels` | `output`：总输出各声道峰值（dBFS）；`meters`：每根电平条的峰值（dBFS，−120 表示无声），顺序与 `status.current.meters` 一致 | 10 次/秒；不发声的记录型引擎给出模拟值（有声部在响的条为 −18） |
| `leds` | `colors`：十六进制字符串，每颗灯 6 个字符 `rrggbb`，按逻辑位置排列；逻辑位置 0 在 12 点方向，未施加灯带偏移 | 与灯光引擎同频（60 次/秒），只在颜色变化时 |
| `mat` | `t`、`source`（`controller` 或 `virtual`）、`pressure`（224 个整数，压力 × 1000）、`occupied`（有石头的区域序号）、`ringCounts`、`control`（控制区压力，未声明为 `null`） | 垫面变化时，最多 30 次/秒 |

推送由数据变化唤醒，不按固定间隔轮询，所以灯环预览不会因为两边节奏错开而丢帧。客户端把 `patch` 逐条应用到 `hello` 给出的状态树上。断开后客户端丢弃全部实时数据，重连后重新收到 `hello`。

## 状态树

状态中心的树分为 `status`（运行状态，由各模块写入）、`settings`（持久设置，结构见下）和 `catalog`（可用的编排和录制）。每一段只有一个模块写，登记在 `soundmat/store/branches.py`（见 `HOST_PROGRAM.md`「状态树的写入者」）。当前已有的路径：

| 路径 | 含义 |
|---|---|
| `status.current.virtual` | 是否使用虚拟垫子 |
| `status.current.arrangement`、`status.current.mode` | 当前编排标识与模式名 |
| `status.current.modeStatus` | 模式状态 `{text, reading, transport}` |
| `status.current.switching` | 切换中为 `{from, to, progress}`，否则 `null` |
| `status.current.meters` | 当前编排的电平条 `[{id, label, group, ring, color}]`：`group` 为 `background` 或 `placed`，背景组在前；`ring` 是只对应一个环时的环号（控制台用这一环的颜色），否则为 `null`；`color` 是编排指定的 `#rrggbb` 或 `null` |
| `status.engine` | 声音引擎：在响声部数 `voices`、预算 `budget`、各类别在响数 `categories`、让位 `yields`、放弃 `rejected`、迟到 `late`、去重 `duplicates`、合成器服务重启 `restarts` |
| `status.log` | 最近的警告和错误：`[{at, level, text, count?}]`，最新在前 |
| `status.assets` | `missing`（当前编排缺失的素材）、`needed`（引用总数）、`state`（`loaded`、`memoryMB`、`budgetMB`、`library`） |
| `status.mat` | 控制器链路：`connected`、`port`、`fps`（实测传感帧率）、`checksumErrors`、`problem`（问题说明）、`source`（`controller` 或 `virtual`；虚拟垫子时其余项为 `null`） |
| `status.health` | 状态指示：`sound`、`mat`、`net` 各为 `{level, reason}`（`ok` / `warn` / `error` / `unknown`），`overall` 为最严重的一项，`issues` 为"声音：原因"形式的列表 |
| `status.audio.service`、`status.audio.usbCard` | 音频服务是否运行、是否有 USB 声卡（未知为 `null`） |
| `status.audio.synth` | 合成器服务：`online`、`synthdefsLoaded`、`sampleRate`、`avgLoad`、`peakLoad` |
| `status.audio.outputDevice` | 实际输出设备 `{name, usb}` |
| `status.audio.channels`、`status.audio.buffer`、`status.audio.xruns`、`status.audio.xrunsSinceStart`、`status.audio.loadHistory` | 声道数、缓冲 `{period, periods, driver}`、卡顿次数（从主机程序和 JACK 里较晚的那次启动算起、最长一小时；`xrunsSinceStart` 为真时表示不满一小时、从启动算起）、最近 60 秒负载 |
| `status.matHistory` | 最近 60 秒的实测传感帧率 |
| `status.rates` | 各条链路的帧率，每项为 `{actual, expected}`（次/秒，没有这条链路或没有数据时为 `null`）：`sensing`（控制器传感）、`perception`（垫面解读）、`beat`（声音化节拍）、`light`（灯光引擎）、`ledWrites`（写给控制器的灯光帧）、`pushMat`、`pushLeds`（推送到控制台，取所有连接里最高的一个；只在有变化时推送，期望值是上限） |
| `status.timing` | `stalls`（节拍晚到超过迟到容忍度）、`late`、`yields`、`rejected` 的累计数，各自带 `…Recent`（最近 1 分钟的增加量）；`maxLagMs`（最近 1 分钟最大的节拍延迟）；`synthLate`（最近 1 分钟合成器服务收到太晚的指令数，读不到日志时为 `null`）；`stallsAttention`、`lateAttention`、`synthLateAttention`（是否达到需要注意的程度） |
| `status.program` | 主机程序：`uptime`（秒）、`restarts`（systemd 自动重启次数，不在 systemd 下为 `null`）、`version`（`{commit, deployedAt, dirty, source}`，`source` 为 `deploy` 或 `git`；都读不到为 `null`） |
| `status.maintenance` | `{enabled}`：能否从控制台重启（只在 systemd 下运行时） |
| `status.update` | 软件更新：`enabled`（是否从发布包、在 systemd 下运行）、`state`（`idle` / `downloading` / `installing` / `restarting` / `error`）、`message`、`previous`（可以回到的上一版）、`pending`（待确认的新版本）、`failed`（启动失败被自动回退的版本） |
| `status.storage` | 录音空间：`freeGB`、`minutes`（按当前声道数和分轨设置还能录的分钟数，不录音频时为 `null`） |
| `status.machine` | `host`、`model`、`tempC`、`throttled`、`memUsedMB`、`memTotalMB`、`diskFreeGB`、`diskTotalGB`、`uptime`、`programUptime`、`programCpu`（主机程序占单核的百分比，可超过 100%）、`programCpuHistory`（最近 60 秒）、`cpu`（整机所有核的平均百分比，不是 Linux 时为 `null`）、`cores` |
| `status.network` | `name`、`type`、`address`、`tailscale`、`tailscaleAddress`、`localName`（局域网名字，主机名已带 `.local` 时不再追加）、`line`（垫面页顶部显示的一行）、`kind`（`phoneHotspot` / `selfHotspot` / `external` / `wired`，按配置 `[network]` 的连接名区分）、`apClients`（自建热点开着时大约连着的设备数，否则 `null`） |
| `status.recording` | `{state}`，`state` 为 `idle` / `countdown` / `recording`；录制中另有 `count`（倒计时数字）、`flash`（打板的一瞬）、`elapsed`、`folder`、`audio`、`freeGB` |
| `catalog.recordings` | `[{name, startedAt, title, duration, audio}]`，最新在前 |
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
| `POST /api/audio/test-tone` | `{"channel": 声道序号}` | 在该硬件声道放 1 秒测试音；超出当前音箱布局返回 422 |
| `GET /api/update` | — | `{allowed, enabled, available, error}`：`available` 是 GitHub 上的发布包 `[{tag, commit, branch, builtAt, current}]`，最新在前，只在 `allowed` 时列出；`allowed` 只对本机和 Tailscale（100.64.0.0/10）的请求为真 |
| `POST /api/update` | `{"tag": "build-<短提交号>"}` | 在后台下载、安装并切换到这个版本，之后主机程序重新启动；不是本机或 Tailscale 来的请求返回 403，不能更新或正在更新返回 409 |
| `POST /api/update/rollback` | — | 切回上一版并重新启动；权限与返回同上 |
| `POST /api/system/restart` | `{"target": "sound" \| "program" \| "machine"}` | 重启声音（JACK 和合成器服务）、主机程序或整台机器，交给 systemd 执行，返回 202；不在 systemd 下运行（开发机）或系统权限不足返回 409 和原因，不认识的对象返回 422 |
| `POST /api/recording/start` | — | 开始录制；空间不足、已在录制或合成器服务没有响应时返回 409 和原因 |
| `POST /api/recording/stop` | — | 停止录制 |
| `GET /api/recordings` | — | 录制列表 |
| `GET /api/recordings/{name}/download` | — | 整个录制文件夹打包成 zip 下载 |
| `POST /api/recordings/{name}/delete` | — | 删除一段录制（整个文件夹，不可恢复）；正在录的那一段返回 409，不存在返回 404 |
| `POST /api/settings` | `{"changes": {"sound.volume": 0.7, ...}}` | 修改设置（键是 `settings` 下的路径；`sound.layout` 也可以是预设名 `stereo` / `quad` / `octo`）；任一项非法返回 422，整批不生效 |
