# Deployment

本文说明部署好的 SoundMat 主机是什么样、为什么这样安排：装了哪些服务、文件放在哪、程序怎样经 GitHub 更新、网络怎样选择、音频和电源的参数，以及交付前的验收标准。从空白存储卡开始的操作步骤、命令和排错，写在部署 skill **`skills/soundmat-deploy/SKILL.md`** 里（2026-10 在 Pi 5 和 Pi 3B 上实际走通）。

部署出来的主机只依赖本仓库（经 GitHub 的发布包）和开发机的声音素材库 `SoundMat/sound/`；系统里所有配置文件都来自仓库的 `system/`。

## 组成

| 服务 / 配置 | 来自 | 作用 |
|---|---|---|
| `soundmat-clock.service`、`/usr/local/bin/soundmat-clock` | `system/clock/` | 开机时先等系统时钟校准再启动声音，之后这次开机不再校时，见「时钟」 |
| `jackd.service` | `system/systemd/` | JACK 驱动 USB 声卡（48 kHz，实时优先级） |
| `soundmat-scsynth.service` | `system/systemd/` | 合成器服务，JACK 就绪后启动，自己把输出接到声卡 |
| `soundmat.service` | `system/systemd/` | 主机程序，从 `current` 指向的版本目录启动；启动前运行 `soundmat-guard` |
| `soundmat-net-fallback.timer` | `system/network/` | 每分钟按优先级选择网络、没网时开自建热点 |
| `/etc/systemd/logind.conf.d/soundmat.conf` | `system/systemd/logind-soundmat.conf` | `RemoveIPC=no`，见「音频参数」 |
| `/usr/local/bin/soundmat-guard` | `system/update/` | 新版本反复启动失败时切回上一版 |
| `/etc/polkit-1/rules.d/50-soundmat.rules` | `system/polkit/` | 允许装置用户从控制台重启 JACK、合成器服务、主机程序和整台机器（只放开这几项） |

三个主服务按 JACK → scsynth → 主机程序的顺序依赖（开机时 JACK 之前还有一步等时钟，见「时钟」），异常退出都会自动重启，开机自启。scsynth 是独立的服务而不是主机程序的子进程：主机程序重启（更新、出错后被拉起）时声音链路不中断，scsynth 出错时由 systemd 单独重启、主机程序发现后重建（`SYNTH.md`）。

系统环境：Raspberry Pi OS Lite 64 位；`jackd2`、`supercollider-server`（不装 sclang，音色在开发机编译）；uv 管理的 Python 3.12；Tailscale（设备名 `soundmat-pi`）。

## 树莓派上的目录

| 内容 | 位置 |
|---|---|
| 主机程序、编排、音色、控制台（按版本） | `/home/soundmat/soundmat/releases/<短提交号>/`，`current` 指向正在用的版本 |
| 声音素材 | `/home/soundmat/sound/` |
| 更新状态 | `/home/soundmat/data/update.json` |
| 设置 | `/home/soundmat/data/settings.json` |
| 录音 | `/home/soundmat/data/recordings/` |
| 日志 | systemd journal |

`releases/` 只由更新写入，`data/` 下的内容只由装置自己写入，更新从不碰 `data/` 下的设置和录音。程序目录不在 `sound/` 旁边，所以主机程序的服务用环境变量 `SOUNDMAT_SOUND=/home/soundmat/sound` 和 `--data-dir /home/soundmat/data` 指定这两个位置。

## 发布与更新

程序的每一次更新都经过 GitHub：开发机构建并上传发布包，装置从 GitHub 下载安装，装置上不做任何构建（`DECISION.md` 第 10 条）。

**发布包**是一个 `tar.gz`，包含主机程序（`soundmat/`）、编排、配置、编译好的音色（`instruments/compiled/`）、构建好的控制台（`console/dist/`）、`pyproject.toml` 与 `uv.lock`、`system/`，以及 `VERSION` 文件（第一行提交号，第二行构建时间）。压缩后不到 1 MB。它作为 GitHub 上一个预发布版本的附件存放：标签 `build-<短提交号>`，说明里写分支、完整提交号、构建时间和包的 SHA-256。只保留最近 20 个，更早的连同标签自动删除。

**发布**由开发机上的 `scripts/release.py` 完成：推送、编译音色（没变时跳过）、构建控制台、打包上传、同步素材、通知装置更新，前后约 20–40 秒（用法见部署 skill）。CI 照常在 GitHub 上跑测试，装置不等它。

**在装置上**，程序目录按版本存放：

```
/home/soundmat/soundmat/
├── releases/<短提交号>/    每个版本一个目录，各有自己的 .venv
└── current -> releases/<短提交号>
```

更新时主机程序在后台下载发布包、核对 SHA-256、解压到 `releases/<短提交号>/`、用 `uv sync --frozen --no-dev` 建好环境，全部成功后才把 `current` 原子地指向新目录，然后自己退出，由 systemd 按新版本重新启动；演奏只在重启的十几秒里中断。`releases/` 保留当前版本、上一版和最近的另外一个，更早的删除。

**失败时自动回退**：切换前把"待确认的新版本"和"上一版"写进 `/home/soundmat/data/update.json`。systemd 每次启动主机程序前先运行 `/usr/local/bin/soundmat-guard`（来自 `system/update/`，不随版本更新，所以新版本坏了它也能工作）：待确认的新版本已经启动过 3 次仍未确认，就把 `current` 改回上一版。新版本正常运行 60 秒后自己确认，清除待确认标记。

**谁能更新**：控制台不设登录，所以只有从本机或 Tailscale（100.64.0.0/10）访问的人能发起更新和回退；从手机热点或自建热点打开控制台的人只能看到当前版本。只有在 systemd 下、从 `releases/` 里运行时才能更新，开发机上看不到更新按钮。

## 声音素材

声音素材不放进发布包，也不经过 GitHub：体积大、很少变化，而且仓库是公开的。发布命令每次用 rsync 从开发机直接同步到装置的 `/home/soundmat/sound/samples/`，只同步所有编排实际引用到的文件（`soundmat/updater/samples.py` 从编排里读出，当前 14 个、约 326 MB）。开发机的素材库 `SoundMat/sound/` 有 1.3 GB，其余是原始录音（`raw/`）和待整理的素材，装置用不到。没有变化的文件不传，之后的发布这一步只要一两秒；不删除装置上已有的文件，换掉的旧素材留在装置上也不影响。新编排引用了新素材时，正常发布就会带过去。

编排缺少素材时照常运行，看板和编排面板会列出缺了哪些。

## 网络

树莓派按优先级选择网络：先连手机热点，再按外部网络列表连接场地或开发用的 Wi-Fi，都没有时自建热点。插网线时有线网络始终可用。

| 连接名 | SSID | 密码 | 自动连接 / 优先级 | 用途 |
|---|---|---|---|---|
| `phone-hotspot` | `soundmat` | `soundmat` | 是 / 100 | 手机热点，展出时的主网络 |
| `uw-mpsk` | `UW MPSK` | 用网卡 MAC 在 UW 登记得到，不进仓库 | 是 / 50 | 外部网络：UW 实验室。固定使用网卡出厂 MAC（`cloned-mac-address=permanent`），避免登记失效 |
| `netplan-wlan0-Avocado`（Pi 3B 上叫 `Avocado`） | `Avocado` | 家里的 Wi-Fi 密码，不进仓库 | 是 / 40 | 外部网络：开发用的家庭 Wi-Fi，由 Raspberry Pi Imager 写入，netplan 管理 |
| `netplan-eth0` | — | — | 是 | 有线网络 |
| `soundmat-ap` | `SoundMat-AP` | `soundmat` | 否 | 自建热点，2.4 GHz 信道 6，树莓派地址 `10.42.0.1`，为连上的设备分配地址 |

外部网络列表就是这些开启自动连接的 Wi-Fi 配置，增删一个外部网络只需要增删一个 NetworkManager 连接，并设好优先级。自建热点用 `SoundMat-AP`，不用只差大小写的 `SoundMat`，避免现场和手机热点 `soundmat` 混淆。

**网络选择与兜底**由 `system/network/` 下的脚本 `soundmat-net-fallback` 和它的 systemd 定时任务完成：开机 60 秒后第一次运行，之后每 60 秒运行一次。每次运行：

1. 自建热点开着时扫描 Wi-Fi，看到任一已知网络就关掉热点，连优先级最高的那个。
2. 已连着 Wi-Fi 时，看到优先级更高的已知网络（例如手机热点刚打开）就切过去。NetworkManager 自己只在建立连接时比较优先级，已连上后不会主动切换。
3. Wi-Fi 和有线都没有连接、也不在连接中时，开启自建热点。

自建热点需要 `wifi-sec.proto rsn`、`pairwise ccmp`、`group ccmp`、`pmf disable`，以适配树莓派的无线芯片。

**实测耗时**（2026-10-17，Pi 5）：已连 Avocado 时打开手机热点，下一次运行即切换，连接用时约 4 秒。关掉手机热点后，NetworkManager 先重试约 80 秒（两次各 25 秒的关联超时），之后下一次运行开启自建热点，1 秒内就绪；按 60 秒间隔，从断网到热点出现最多约 2 分 20 秒。自建热点开着时可以正常扫描，已知网络回来后下一次运行即切回。开机时周围没有已知网络，NetworkManager 不会尝试连接，60 秒后热点出现。

## 时钟

树莓派没有电池时钟：开机时用上次关机时存下的时间，联网校时会让时钟一下跳几分钟到几天。合成器服务按墙钟时间执行带时间戳的指令，时钟在它运行时跳变会打乱定时；2026-10-18 在 Pi 3B 上，校时跳了 276 秒，合成器要过一阵才跟上，期间带时间戳的"开始"被压住、立即的"停止"先执行，留下停不下来的和声铺底，负载升到 97%（`DECISION.md` 第 12 条）。

所以开机时 `soundmat-clock` 排在 JACK 之前运行一次：有网就等到校准完成（通常开机后约 30 秒），最多等 45 秒；开机 20 秒后还没有任何网络连接（没有默认路由，例如只有自建热点）就不再等。然后停掉 `systemd-timesyncd`：声音启动之后，这次开机不再校时，时钟不会再跳；下次开机照常校时。开机没网时，这次开机用的是上次关机时存下的旧时间，录音文件夹上的日期时间可能不准，看板「机器」里的"系统时间"会写明未校准。

这一步让开机到出声多了约 20–45 秒。主机程序另有一层保护：发现墙钟跳变（例如有人手动改时间）时，之后 120 秒内所有指令立即执行（合成器要一分多钟才对齐时钟），不会留下停不下来的声音。

## 音频参数

采样率使用 48 kHz，与声音素材库一致，避免实时重采样。

JACK 先使用在 Pi 3B 上验证过的设置：每块 2048 帧、两块缓冲。Pi 5 性能更强，应在看板上观察音频卡顿次数，逐步降到 1024 或 512 以减少延迟。scsynth 的内部块大小保持默认的 64：调大会让包络和鼓的起音变得阶梯化，省下的计算很少（见系列文档第 16 篇）。CPU 紧张时优先降低声部预算，最后才加大 JACK 缓冲。

JACK 以实时优先级运行：服务里必须有 `LimitRTPRIO=95`、`LimitMEMLOCK=infinity`，否则 JACK 退回普通优先级（日志 `Cannot use real-time scheduling`），容易卡顿；第一版在 Pi 3B 上一直缺这一项。JACK 以普通用户 `soundmat` 运行，所以 logind 要设 `RemoveIPC=no`：默认情况下这个用户最后一个登录会话（例如 SSH）结束时，systemd 会清掉它的共享内存和信号量，JACK 随即失效（`semop (Invalid argument)`）。

## 电源

装置的电源是 USB-C PD 诱骗到 20 V，经降压模块得到 5 V（约 5.06 V），分两路：一路给灯带（独立供电，两端接入），一路经 USB 头给树莓派。Pi 5 用 USB-C 公头（CC 脚带 56 kΩ 电阻），和给 Pi 3B 的 Micro USB 头并联在降压模块输出上。降压模块不和 Pi 5 协商快充，Pi 5 因此把 USB 总输出限制在 600 mA；保持这个限制：USB 声卡加 ESP32 只要约 0.2–0.5 A，限制还能防止 USB 设备多抽电、减轻接头的负担。实测 5 V 总线（含灯带）在 Jam 中约 0.8 A，开机时固件让灯带全亮约 5 秒，约 3.8 A。

灯带的信号线只接数据和地（灯带一侧的红线已剪断），信号接头插反不会短路。

## 验收标准

部署完成后全部满足，这台主机才可以交付（检查方法见部署 skill）：

1. JACK、scsynth、主机程序三个服务和网络定时任务都在运行；JACK 以实时优先级运行，scsynth 的输出接到了声卡。
2. 局域网 `http://soundmat-pi.local:8000` 和 Tailscale `http://soundmat-pi:8000` 都能打开控制台。
3. 看板一切正常：合成器服务使用 USB 声卡、48 kHz、音色全部加载；控制器已连接，传感帧率 25–30；网络正常。
4. 逐声道测试音从对应的音箱发出。
5. 在垫子上放石头，听到声音、看到灯光反馈，控制台垫面上的位置与实物一致。
6. 断电后重新上电，装置自己进入默认编排，看板恢复正常。
7. 关掉手机热点后，自建热点在约 2 分钟内出现，手机连上能打开控制台；再打开手机热点，约一分钟内切回。
8. Pi 5 在负载下输入电压不低于 4.9 V，没有欠压；连续运行一小时温度低于 80°C。
9. 从控制台重启声音，约 5 秒后声音恢复；重启程序，控制台自己重连。
10. 播放 Jam 时，合成器服务收到太晚的定时指令接近 0（看板「节奏」）。
