# Deployment

本文说明怎样从一块空白存储卡得到一台可以演奏的 SoundMat 主机，以及之后怎样更新。全部步骤只依赖三样东西：本仓库、开发机上的声音素材库 `SoundMat/sound/`，以及一个不进仓库的密钥文件。执行的工作由 `deploy/` 下的部署脚本完成，它要安装到系统里的配置文件都放在 `system/`；本文解释脚本做了什么、为什么这样做、怎样验证。

部署脚本可以重复运行。第一次运行完成全新安装，之后每次运行只更新变化的部分，不会覆盖设置和录音。

## 准备

**开发机**需要：本仓库、`SoundMat/sound/` 声音素材库、uv、SuperCollider（用 sclang 编译音色）、一对 SSH 密钥。

**硬件**：Raspberry Pi 5（配主动散热器，装置的空腔是封闭的）、存储卡、USB 声卡、ESP32 控制器、音箱。

**密钥文件**是开发机上的 `deploy/secrets.env`，必须列入 `.gitignore`，永远不提交。仓库里的 `deploy/secrets.example.env` 列出需要填写的项：

1. UW MPSK 为这台设备登记得到的密码。
2. Tailscale 的授权密钥（可选；没有时用浏览器登录授权）。

手机热点和自建热点的名称和密码是固定的，直接写在下面的「网络」一节，不放进密钥文件（见 `DECISION.md` 第 6 条）。

## 第一步：烧录系统

用 Raspberry Pi Imager 烧录 Raspberry Pi OS Lite（64 位），并在烧录设置里预先填好：

1. 主机名 `soundmat-pi`，用户名 `soundmat`。
2. 只允许 SSH 密钥登录，填入开发机的公钥。
3. Wi-Fi 填手机热点，保证第一次开机就能连上网络。
4. 时区设为 America/Los_Angeles，录制信息里的时间依赖它。

插卡通电，等一两分钟，在开发机上确认能用 `ssh soundmat@soundmat-pi.local` 登录。

在 UW 使用 UW MPSK 前，需要用这台设备无线网卡的固定 MAC 地址登记（地址可以在 `/sys/class/net/wlan0/address` 查到）。部署脚本会让这个连接始终使用固定地址，不做随机化，否则登记会失效。

## 第二步：运行部署脚本

在开发机上运行部署脚本，参数是树莓派的地址（`soundmat-pi.local`，或它在 Tailscale 里的名字 `soundmat-pi`）。脚本通过 SSH 依次完成下面的工作。

1. **系统软件包**：安装 SuperCollider 的合成器服务（scsynth）、JACK2、avahi、rsync 等。树莓派上不需要 sclang。
2. **实时音频权限**：把 `soundmat` 用户加入 `audio` 组，并允许它以实时优先级运行音频服务。
3. **电源设置**：降压模块只输出 5V，不和 Pi 5 协商快充，Pi 5 默认会把 USB 总输出限制在 600 mA。在确认电源能提供足够电流的前提下，于 `/boot/firmware/config.txt` 打开 `usb_max_current_enable`，避免 USB 声卡和 ESP32 供电不足。
4. **Python 环境**：安装 uv，由它安装 Python 和依赖，不使用系统自带的 Python。
5. **程序与数据**：按下面「发布与更新」一节，从 GitHub 安装第一个发布包；把开发机的 `SoundMat/sound/` 用 rsync 同步到树莓派的声音素材目录（素材不经过 GitHub，见「声音素材」）。
6. **系统服务**：安装 `system/systemd/` 下的三个服务，依次是 JACK、scsynth、主机程序，后一个依赖前一个，任何一个异常退出都会自动重启，并设为开机启动。
7. **网络**：按下面「网络」一节建立 NetworkManager 连接，安装 `system/network/` 下的网络选择与兜底定时任务。avahi 随系统启用，局域网内可以用 `soundmat-pi.local` 访问。
8. **Tailscale**：从 Tailscale 官方 apt 源安装，用密钥文件里的授权密钥加入网络；没有授权密钥时由 `tailscale up` 打印登录链接，在浏览器里授权。设备名 `soundmat-pi`。
9. **设置**：树莓派上还没有设置文件时，写入一份默认设置；已有时保持不动。
10. **收尾**：重启有变化的服务，打印各服务状态和控制台地址。

## 第三步：验证

部署完成后逐项确认，全部通过才算这台主机可以交付：

1. 三个系统服务都在运行。
2. 在局域网里用 `http://soundmat-pi.local:8000` 能打开控制台；在别处通过 Tailscale 也能打开。
3. 看板上声音、垫子、网络三项都正常；合成器服务实际使用的是 USB 声卡，采样率和声道数与设置一致；垫子一栏显示实测传感帧率。
4. 逐声道测试音从对应的音箱发出。
5. 在垫子上放一颗石头，听到声音、看到灯光反馈。
6. 断电后重新上电，装置自己进入默认编排，看板恢复正常。
7. 关掉手机热点后重启，等待超时后自建热点出现，手机连上它能打开控制台；再打开手机热点，一分钟左右树莓派切回手机热点。

## 发布与更新

程序的每一次更新都经过 GitHub：开发机构建并上传发布包，装置从 GitHub 下载安装，装置上不做任何构建（`DECISION.md` 第 10 条）。

**发布包**是一个 `tar.gz`，包含主机程序（`soundmat/`）、编排、配置、编译好的音色（`instruments/compiled/`）、构建好的控制台（`console/dist/`）、`pyproject.toml` 与 `uv.lock`、`system/`，以及 `VERSION` 文件（第一行提交号，第二行构建时间）。压缩后不到 1 MB。它作为 GitHub 上一个预发布版本的附件存放：标签 `build-<短提交号>`，说明里写分支、完整提交号、构建时间和包的 SHA-256。只保留最近 20 个，更早的连同标签自动删除。

**在开发机上发布**：提交并推送后运行

```bash
uv run python scripts/release.py
```

它依次检查工作区没有未提交的改动，推送当前分支，编译音色（源码没变时跳过），构建控制台，打包并上传，然后通过 Tailscale 通知装置（默认 `soundmat-pi`，`--device` 指定其他名字，`--no-update` 只发布不通知）更新到这个版本，等装置报告新版本已运行后结束。前后约 20–30 秒。CI 照常在 GitHub 上跑测试，装置不等它。

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

声音素材（`SoundMat/sound/`，约 1.3 GB）不放进发布包，也不经过 GitHub：它很少变化，而且仓库是公开的。第一次部署或增加素材时，从开发机同步：

```bash
rsync -a --delete ~/Projects/SoundMat/sound/ soundmat@soundmat-pi:/home/soundmat/sound/
```

编排缺少素材时照常运行，看板和编排面板会列出缺了哪些。

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

## 音频参数

采样率使用 48 kHz，与声音素材库一致，避免实时重采样。

JACK 先使用在 Pi 3B 上验证过的设置：每块 2048 帧、两块缓冲。Pi 5 性能更强，应在看板上观察音频卡顿次数，逐步降到 1024 或 512 以减少延迟。scsynth 的内部块大小保持默认的 64：调大会让包络和鼓的起音变得阶梯化，省下的计算很少（见系列文档第 16 篇）。CPU 紧张时优先降低声部预算，最后才加大 JACK 缓冲。

## 网络

树莓派按优先级选择网络：先连手机热点，再按外部网络列表连接场地或开发用的 Wi-Fi，都没有时自建热点。插网线时有线网络始终可用。

| 连接名 | SSID | 密码 | 自动连接 / 优先级 | 用途 |
|---|---|---|---|---|
| `phone-hotspot` | `soundmat` | `soundmat` | 是 / 100 | 手机热点，展出时的主网络 |
| `uw-mpsk` | `UW MPSK` | 登记得到，放在密钥文件 | 是 / 50 | 外部网络：UW 实验室。固定使用网卡出厂 MAC（`cloned-mac-address=permanent`），避免登记失效 |
| `netplan-wlan0-Avocado` | `Avocado` | 烧录时写入 | 是 / 40 | 外部网络：开发用的家庭 Wi-Fi，由 Raspberry Pi Imager 写入，netplan 管理 |
| `netplan-eth0` | — | — | 是 | 有线网络 |
| `soundmat-ap` | `SoundMat-AP` | `soundmat` | 否 | 自建热点，2.4 GHz 信道 6，树莓派地址 `10.42.0.1`，为连上的设备分配地址 |

外部网络列表就是这些开启自动连接的 Wi-Fi 配置，增删一个外部网络只需要增删一个 NetworkManager 连接，并设好优先级。自建热点用 `SoundMat-AP`，不用只差大小写的 `SoundMat`，避免现场和手机热点 `soundmat` 混淆。

**网络选择与兜底**由 `system/network/` 下的脚本 `soundmat-net-fallback` 和它的 systemd 定时任务完成：开机 60 秒后第一次运行，之后每 60 秒运行一次。每次运行：

1. 自建热点开着时扫描 Wi-Fi，看到任一已知网络就关掉热点，连优先级最高的那个。
2. 已连着 Wi-Fi 时，看到优先级更高的已知网络（例如手机热点刚打开）就切过去。NetworkManager 自己只在建立连接时比较优先级，已连上后不会主动切换。
3. Wi-Fi 和有线都没有连接、也不在连接中时，开启自建热点。

安装：脚本放到 `/usr/local/sbin/soundmat-net-fallback`，`.service` 和 `.timer` 放到 `/etc/systemd/system/`，启用 `soundmat-net-fallback.timer`。建立连接时可以先不填密码，再用 `nmcli con modify <连接名> wifi-sec.psk <密码>` 补上。自建热点需要 `wifi-sec.proto rsn`、`pairwise ccmp`、`group ccmp`、`pmf disable`，以适配树莓派的无线芯片。

**实测耗时**（2026-10-17，Pi 5）：已连 Avocado 时打开手机热点，下一次运行即切换，连接用时约 4 秒。关掉手机热点后，NetworkManager 先重试约 80 秒（两次各 25 秒的关联超时），之后下一次运行开启自建热点，1 秒内就绪；按 60 秒间隔，从断网到热点出现最多约 2 分 20 秒。自建热点开着时可以正常扫描，已知网络回来后下一次运行即切回。开机时周围没有已知网络，NetworkManager 不会尝试连接，60 秒后热点出现。

改网络配置可能让 SSH 断开。不插网线时，切换前先用 `sudo systemd-run --on-active=8m nmcli con modify ...` 预约一次回滚。
