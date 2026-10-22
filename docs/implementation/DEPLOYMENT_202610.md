# Pi 5 部署记录 · 202610

复制自 [DEPLOYMENT.md](DEPLOYMENT.md)，用于记录本次实际部署。完成并确认一步后，将对应的 `[ ]` 改为 `[x]`，在该项下补充日期、结果或问题；未验证的步骤保持未勾选。以下部署脚本与服务行为是待实现、待验证的方案，不表示已经可用。

## 本次进度

- [x] Pi 5 到货 — 2026-10-16，用户确认。
- [x] 确认主动散热器、存储卡、电源及所需外设齐备。— 2026-10-19：主动散热器、32GB microSD、USB 声卡；装置电源经焊接的 USB-C 头供电（实测 5.08 V）；ESP32 控制器当晚从 Pi 3B 换到 Pi 5。
- [x] 确认开发机上的仓库、声音素材库、uv、SuperCollider 和 SSH 密钥可用。— 2026-10-19，在开发机上用 `scripts/release.py` 发布、同步素材成功。
- [ ] 备份 Pi 3B 的开机自启配置。
- [x] 完成新版主机程序及部署脚本、系统服务配置，具备第二步部署条件。— 部署脚本没有写：改为按部署 skill（`skills/soundmat-deploy/SKILL.md`）手动安装，用 `scripts/release.py` 发布，见第二步各项。

## 原部署说明


本文说明怎样从一块空白存储卡得到一台可以演奏的 SoundMat 主机，以及之后怎样更新。全部步骤只依赖三样东西：本仓库、开发机上的声音素材库 `SoundMat/sound/`，以及一个不进仓库的密钥文件。执行的工作由 `deploy/` 下的部署脚本完成，它要安装到系统里的配置文件都放在 `system/`；本文解释脚本做了什么、为什么这样做、怎样验证。

部署脚本可以重复运行。第一次运行完成全新安装，之后每次运行只更新变化的部分，不会覆盖设置和录音。

## 准备

**开发机**需要：本仓库、`SoundMat/sound/` 声音素材库、uv、SuperCollider（用 sclang 编译音色）、一对 SSH 密钥。

**硬件**：Raspberry Pi 5（配主动散热器，装置的空腔是封闭的）、存储卡、USB 声卡、ESP32 控制器、音箱。

**密钥文件**是开发机上的 `deploy/secrets.env`，必须列入 `.gitignore`，永远不提交。仓库里的 `deploy/secrets.example.env` 列出需要填写的项：

- [x] 手机热点的名称和密码。— 2026-10-17 改为直接写进文档（`DECISION.md` 第 6 条）：SSID `soundmat`，密码 `soundmat`。
- [x] 自建热点的名称和密码。— 同上：SSID `SoundMat-AP`，密码 `soundmat`。
- [x] UW MPSK 的名称和为这台设备登记得到的密码。— 2026-10-19 在 UW 登记了 Pi 5 的出厂 MAC `98:fe:54:22:58:26`（2031-10-18 到期），密码由用户在终端里填入装置，不进仓库。
- [x] Tailscale 的授权密钥。— 本次不需要，改为浏览器登录授权。

## 第一步：烧录系统

- [x] 用 Raspberry Pi Imager 烧录 Raspberry Pi OS Lite（64 位）— 2026-10-16，用户提供 Write complete 截图，存储已自动弹出；本次选用 32GB microSD。

烧录设置：

- [x] 主机名 `soundmat-pi`，用户名 `soundmat` — 用户提供配置，完成截图确认主机名和用户设置已应用；待开机验证。
- [x] 开启 SSH — 2026-10-16，完成截图确认已启用。
- [x] 配置并验证 SSH 公钥登录 — 2026-10-16，Mac 通过 BatchMode SSH 成功执行系统检查。
- [x] 写入 Wi-Fi 配置 — 2026-10-16，完成截图确认已应用；具体 SSID 和实际联网待验证。
- [x] 时区设为 America/Los_Angeles — 2026-10-16，timedatectl 实测确认。

- [x] 插卡通电，在开发机上确认能用 `ssh soundmat@soundmat-pi.local` 登录 — 2026-10-16，实测主机名 soundmat-pi、系统 Debian 13 (trixie)、架构 aarch64；局域网连接正常。

首次检查（2026-10-16）：使用支持 5V/3A 的 PD 充电宝供电；`get_throttled=0x0`，当前启动未记录欠压或降频；温度 36.2°C。根分区 29GiB，已用 2.0GiB，可用 25GiB。尚未在 PATH 中找到 jackd、scsynth、uv，音频环境待安装。上述供电结果仅覆盖当前空闲状态。

- [x] 在 UW 使用 UW MPSK 前，用这台设备无线网卡的固定 MAC 地址登记（地址可以在 `/sys/class/net/wlan0/address` 查到）。部署脚本会让这个连接始终使用固定地址，不做随机化，否则登记会失效。— 2026-10-19，用户用 NetID `hlxue` 在 <https://register.wifi.uw.edu/guest/mac_create.php> 登记了 Pi 5 的 `98:fe:54:22:58:26`（角色 Student），2031-10-18 23:03 到期；登记回执上的密码不进仓库。

## 第二步：运行部署脚本

在开发机上运行部署脚本，参数是树莓派的地址（`soundmat.local`，或它在 Tailscale 里的名字）。脚本通过 SSH 依次完成下面的工作。

- [x] **系统软件包**：安装 SuperCollider 的合成器服务（scsynth）、JACK2、avahi、rsync 等。树莓派上不需要 sclang。— 2026-10-17，手动执行（未写部署脚本）：`apt-get install --no-install-recommends jackd2 supercollider-server`，得到 jackd2 1.9.22、scsynth 3.13.0；带 recommends 会多装约 140 个桌面相关包。avahi、rsync 系统已自带。已用 dummy 驱动验证 jackd 以实时模式启动、scsynth 作为 JACK 客户端在 48 kHz 下 server ready。
- [x] **实时音频权限**：把 `soundmat` 用户加入 `audio` 组，并允许它以实时优先级运行音频服务。— 2026-10-17，`soundmat` 原本就在 `audio` 组；安装前预设 debconf `jackd2 jackd/tweak_rt_limits=true`，生成 `/etc/security/limits.d/audio.conf`，新登录会话实测 rtprio 95、memlock unlimited。
- [ ] **电源设置**：降压模块只输出 5V，不和 Pi 5 协商快充，Pi 5 默认会把 USB 总输出限制在 600 mA。在确认电源能提供足够电流的前提下，于 `/boot/firmware/config.txt` 打开 `usb_max_current_enable`，避免 USB 声卡和 ESP32 供电不足。
- [x] **Python 环境**：安装 uv，由它安装 Python 和依赖，不使用系统自带的 Python。— 2026-10-17，uv 0.13.1 装在 `~/.local/bin`，`uv python install 3.12` 得到 CPython 3.12.15。非交互 SSH 不加载 PATH，需写完整路径 `~/.local/bin/uv`。依赖要等程序同步后再安装。
- [x] **程序与数据**：用 rsync 把主机程序、编排、编译好的音色同步到树莓派；把开发机的 `SoundMat/sound/` 同步到树莓派的声音素材目录。— 2026-10-19，先手动装了发布包 `e2af493`，之后用 `scripts/release.py --device soundmat-pi` 发布 `c77653a`，同步素材 14 个文件 326 MB（经 UW MPSK，77 秒）。
- [x] **系统服务**：安装 `system/systemd/` 下的三个服务，依次是 JACK、scsynth、主机程序，后一个依赖前一个，任何一个异常退出都会自动重启，并设为开机启动。— 2026-10-19，按部署 skill 第 4 节安装（另有 `soundmat-clock`、logind 配置、`soundmat-guard`、polkit 规则）。trixie 的 jackd2 不带 `jack_lsp`，scsynth 服务的启动检查一直报 "JACK not ready"，补装 `jack-example-tools` 后正常，已写进 skill。JACK 实时模式，`jack_lsp -c` 显示 SuperCollider 输出接到 `system:playback_1/2`，`pkcheck` 通过。
- [x] **网络**：按密钥文件建立 NetworkManager 连接：手机热点优先级最高，UW MPSK 次之；自建热点默认不自动连接，由一个开机后等待一段时间仍未联网就启用它的服务兜底。同时设置主机名并启用 avahi，使局域网内可以用 `soundmat.local` 访问。— 2026-10-17，按 `DEPLOYMENT.md`「网络」一节手动完成，没有写部署脚本：建立 `phone-hotspot`（100）、`uw-mpsk`（50，固定出厂 MAC，2026-10-19 已登记、填好密码并实测，见第一步）、`soundmat-ap`（不自动连接）三个连接，Avocado 优先级设为 40；安装 `system/network/` 下的 `soundmat-net-fallback` 及其 timer（开机 60 秒后首次运行，之后每 60 秒一次）。两个热点的密码由用户在终端里填入。主机名保持 `soundmat-pi`，avahi 原已启用。
  - 实测：已连 Avocado 时打开手机热点，下一次检查即切换，用时约 4 秒，外网和 Tailscale 正常。关掉手机热点（同时临时关闭 Avocado 自动连接，并预约 8 分钟后回滚）后，NetworkManager 重试约 80 秒，之后下一次检查开启 `SoundMat-AP`，手机能连上。AP 模式下扫描正常，Avocado 恢复后下一次检查即切回，用时 4 秒。当时 timer 间隔是 2 分钟，之后改为 60 秒，改后未重测。
- [x] **Tailscale**：安装 Tailscale，用密钥文件里的授权密钥加入网络，设备名 `soundmat`。— 2026-10-17，从官方 trixie apt 源装 1.104.1；没有用授权密钥，而是由 `tailscale up` 打印登录链接、用户在浏览器授权。设备名实际为 `soundmat-pi`，与主机名一致（旧节点已改名为 `soundmat-pi-old`），地址 100.90.172.113，Mac 用 `ssh soundmat@soundmat-pi` 可以登录。节点密钥 2027-04-15 到期。
- [ ] **设置**：树莓派上还没有设置文件时，写入一份默认设置；已有时保持不动。
- [ ] **收尾**：重启有变化的服务，打印各服务状态和控制台地址。

## 第三步：验证

部署完成后逐项确认，全部通过才算这台主机可以交付：

- [x] 三个系统服务都在运行。— 2026-10-19
- [ ] 在局域网里用 `http://soundmat.local:8000` 能打开控制台；在别处通过 Tailscale 也能打开。— 主机名是 `soundmat-pi`，局域网地址应为 `http://soundmat-pi.local:8000`，还没在局域网里实测；Tailscale `http://soundmat-pi:8000` 2026-10-21 在开发机上实测能打开。
- [ ] 看板上声音、垫子、网络三项都正常；合成器服务实际使用的是 USB 声卡，采样率和声道数与设置一致；垫子一栏显示实测传感帧率。— 2026-10-21 实测传感 28 帧/秒、垫面解读 28、节拍 60，JACK 用的是 USB 声卡 `hw:Audio`、48 kHz；看板三项的状态还没逐项核对。
- [ ] 逐声道测试音从对应的音箱发出。
- [x] 在垫子上放一颗石头，听到声音、看到灯光反馈。— 2026-10-20，用户在真垫子上演奏《冥想》并拍摄。
- [x] 断电后重新上电，装置自己进入默认编排，看板恢复正常。— 2026-10-20 多次断电重启（00:19、00:35、00:43、04:30），主机程序都自动开始演奏当时的默认编排《冥想》，控制器自动连上。
- [x] UW MPSK 能连上、Tailscale 可达。— 2026-10-19 实测通过：切到 `uw-mpsk` 后外网正常、Tailscale 直连；恢复选网 timer 后自动回到手机热点。
- [ ] 关掉手机热点后重启，等待超时后自建热点出现，手机连上它能打开控制台。

## 日常更新

改了代码、编排或音色后，重新运行同一个部署脚本即可。脚本默认只同步程序、编排和音色，并重启主机程序；同步声音素材和重新安装系统配置需要显式指定，因为前者耗时，后者会重启音频服务。

## 树莓派上的目录

| 内容 | 位置 |
|---|---|
| 主机程序、编排、音色 | `/home/soundmat/soundmat/` |
| 声音素材 | `/home/soundmat/sound/` |
| 设置 | `/home/soundmat/data/settings.json` |
| 录音 | `/home/soundmat/data/recordings/` |
| 日志 | systemd journal |

程序目录可以随时被部署覆盖，`data/` 下的内容只由装置自己写入，部署从不覆盖。

## 音频参数

采样率使用 48 kHz，与声音素材库一致，避免实时重采样。

JACK 先使用在 Pi 3B 上验证过的设置：每块 2048 帧、两块缓冲。Pi 5 性能更强，应在看板上观察音频卡顿次数，逐步降到 1024 或 512 以减少延迟。scsynth 的内部块大小保持默认的 64：调大会让包络和鼓的起音变得阶梯化，省下的计算很少（见系列文档第 16 篇）。CPU 紧张时优先降低声部预算，最后才加大 JACK 缓冲。

