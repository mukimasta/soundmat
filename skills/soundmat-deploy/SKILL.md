---
name: soundmat-deploy
description: Deploy, update, verify and troubleshoot the SoundMat host on a Raspberry Pi (Pi 5 or the Pi 3B) over SSH from the Mac — from a freshly flashed SD card (power and LED wiring, JACK/scsynth/uv/Tailscale, systemd services, NetworkManager hotspot scheme, first release install) to everyday releases via scripts/release.py, sound sample sync, rollback and the known failure modes. Use when setting up, rebuilding, updating, checking performance of, or debugging the SoundMat Raspberry Pi; or when asked to "部署 / 更新 / 发布到树莓派 / 装置连不上 / 没声音 / 卡".
---

# SoundMat 部署

把 SoundMat 主机程序部署到树莓派，以及之后的更新、验收和排错。所有步骤都在 2026-10-16/17 真机走过：Pi 5 上装了基础环境和网络，Pi 3B 上装了服务、程序、更新流程，并在真垫子上跑了 Jam。部署出来是什么样、为什么这样设计，见 `docs/implementation/DEPLOYMENT.md`；这里只讲怎么做。

## 0. 工作约定

1. **一步一步做，每步验证**，不写一次性的大脚本。装进系统的配置文件都在仓库的 `system/`，从那里 `scp` 过去再 `sudo install`，不要在树莓派上手写配置。
2. **在 `master` 上开发**，提交后推送；程序只通过发布命令进装置（第 6、7 节），不要手改树莓派上 `releases/` 里的文件。
3. **密码由人来输入**，Agent 不经手：
   - sudo：请人在终端运行 `ssh -t soundmat@<主机> 'sudo -v'`。树莓派系统的 sudo 时间戳在会话之间共享（`/etc/sudoers.d/010_global-tty`，`timestamp_type=global`），之后约 15 分钟内 Agent 的非交互 SSH 也能 `sudo -n`；每次用 sudo 会续期，**重启后失效**。先用 `sudo -n true` 确认，再一口气做完需要 sudo 的步骤。
   - Wi-Fi 密码：给人一条在树莓派上提示输入的命令（见第 5 节），不要把密码写进命令行参数或历史。
   - 需要长时间 sudo 时，也可以请人临时开免密 sudo（`/etc/sudoers.d/010-soundmat-nopasswd`），**做完提醒人删掉**；验证"已恢复需要密码"时先 `sudo -k`，否则全局缓存会让 `sudo -n` 仍然成功。
4. **设备记录**：Pi 5 的状态记录在 `~/Worlds/INFRA/Devices/soundmat-pi/`（`state.md` 只写当前状态，`history.md` 追加有意义的变化，规则见同目录 `AGENTS.md`，不写密码）。做之前读 `state.md`，做之后更新它并追加 `history.md`。本次部署的勾选记录在 `docs/implementation/DEPLOYMENT_202610.md`。Pi 3B 即将淘汰，不建设备记录。
5. Agent 的远程命令一律 `ssh -o BatchMode=yes soundmat@<主机> '...'`。非交互 SSH 不加载 `~/.profile`，uv 要写完整路径 `~/.local/bin/uv`。
6. **不要在试听时跑连真实 scsynth 的测试**：`tests/test_scsynth.py` 里那两个测试只在 `SOUNDMAT_LIVE_SCSYNTH=1` 时运行，它们会清空 scsynth 的节点树、发声、录音。

## 1. 主机与地址

| | Pi 5（正式主机） | Pi 3B（过渡，即将淘汰） |
|---|---|---|
| 主机名 / 局域网 | `soundmat-pi` / `soundmat-pi.local` | `soundmat-pi`（同名）/ `soundmat-pi.local` |
| Tailscale | `soundmat-pi`（100.90.172.113） | `soundmat-pi-old`（100.98.12.90） |
| 程序目录 | `/home/soundmat/soundmat/{releases,current}` | `/home/soundmat/sm/{releases,current}`（`~/soundmat` 是保留的第一版） |
| 用户 | `soundmat` | `soundmat` |

两台的主机名一样，同时在同一个局域网里时 `.local` 会冲突，用 Tailscale 名字区分。控制台：`http://<Tailscale 名字>:8000`。

## 2. 烧录与硬件

**烧录**：Raspberry Pi Imager，Raspberry Pi OS Lite（64 位），设置里填：主机名 `soundmat-pi`、用户 `soundmat`、开 SSH 并只用公钥（开发机的 `~/.ssh/id_ed25519.pub`）、Wi-Fi 填家里的 Avocado 或手机热点 `soundmat`、时区 America/Los_Angeles。插卡通电一两分钟后 `ssh soundmat@soundmat-pi.local hostname`。

**known_hosts**：新卡、新设备会和 Mac 上的旧记录冲突。先 `ssh-keyscan -t ed25519 <名字> | ssh-keygen -lf -` 取指纹，和已经信任的地址（例如 `.local`）比对一致；再 `cp ~/.ssh/known_hosts ~/.ssh/known_hosts.bak-<日期>`（`ssh-keygen -R` 会覆盖 `known_hosts.old`），`ssh-keygen -R <名字>`，最后 `ssh -o StrictHostKeyChecking=accept-new` 登录一次。

**供电**：电源是 USB-C PD 诱骗到 20 V，降压模块输出 5 V（调在约 5.06 V），分两路：一路给灯带，一路给树莓派。Pi 5 用焊上的 USB-C 公头（带 56 kΩ CC 电阻的那种，只焊 V 和 G），和给 Pi 3B 的 Micro USB 头**并联在降压模块输出或分线处**（不要焊在 Micro USB 小板的焊盘上），同一时间只插一台。焊好后、插 Pi 之前用万用表确认两个头都是 5.0–5.2 V、正负一致。实测 5 V 总线（含灯带）：Jam 中约 0.8 A，开机灯带全亮约 3.8 A。**保持 Pi 5 默认的 USB 600 mA 限制**，不要打开 `usb_max_current_enable`（声卡加 ESP32 约 0.2–0.5 A）。

**灯带与控制板**：WS2812B，60 颗/米，108 颗，独立从电源板供电（两端供电）。信号线三根：白 = GND，绿 = 数据，红 = 5 V；**灯带一侧的红线已剪断**（控制板上只有数据和地），插反也不会短路，剪下的红线头带电，要包好。数据：ESP32 D13 → 74AHCT125 第 2 脚（1A）→ 第 3 脚（1Y）→ 330 Ω → 灯带 DIN；74AHCT125 第 14 脚 5 V、第 7 脚 GND、第 1 脚（1OE）接 GND；没用的 5、9、12 脚接 GND，4、10、13 脚接 5 V。灯带反接会烧第一颗灯珠，电源板入口的 1000 µF 电解电容反接会鼓包泄压；第一次上电最好用实验室电源限流 0.5 A。

**USB 设备**：USB 声卡 CX31993（ALSA card 名 `Audio`，即 `hw:Audio`，支持 44.1/48/96 kHz）；ESP32 经 CP2102，是 `/dev/ttyUSB0`（`/dev/serial/by-id/usb-Silicon_Labs_CP2102_…`）。确认：`aplay -l`、`ls -l /dev/serial/by-id`、`cat /proc/asound/card0/stream0`。

## 3. 基础环境

需要 sudo（第 0 节）。

```bash
echo "jackd2 jackd/tweak_rt_limits boolean true" | sudo debconf-set-selections
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends jackd2 supercollider-server
```

`--no-install-recommends` 很重要（否则多装约 140 个桌面相关的包）；预设 debconf 会生成 `/etc/security/limits.d/audio.conf`（`@audio` rtprio 95、memlock unlimited）。不装 sclang，音色在 Mac 上编译。

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
~/.local/bin/uv python install 3.12
```

**Tailscale**（trixie 以外替换代号）：

```bash
curl -fsSL https://pkgs.tailscale.com/stable/debian/trixie.noarmor.gpg | sudo tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
curl -fsSL https://pkgs.tailscale.com/stable/debian/trixie.tailscale-keyring.list | sudo tee /etc/apt/sources.list.d/tailscale.list
sudo apt-get update -qq && sudo apt-get install -y -q tailscale
```

登录：用 Bash 的 `run_in_background` 执行 `ssh ... 'sudo tailscale up --hostname=soundmat-pi --timeout=600s'`，输出写到 scratchpad 的日志里，读出 `https://login.tailscale.com/a/...` 交给人在浏览器授权，命令以 `Success.` 结束。tailnet 里已有同名节点时会被命名成 `soundmat-pi-1`：离线的旧节点只能请人在 https://login.tailscale.com/admin/machines 改名（Edit machine name，关掉 Auto-generate），之后 `sudo tailscale set --hostname=soundmat-pi`。节点密钥默认 180 天到期，长期展出请人在后台对这台关掉 key expiry。

验证（重新登录后 limits 才生效）：`ulimit -r`（95）、`ulimit -l`（unlimited）、`jackd --version`、`scsynth -v`、`~/.local/bin/uv run --python 3.12 --no-project python -V`；用 `jackd -R -P75 -d dummy -r 48000 -p 1024 &` 起一个虚拟声卡，`timeout 6 scsynth -u 57199 -i 0 -o 2` 应打印 `server ready`，然后 `pkill jackd`。

## 4. 音频与主机程序的服务

需要 sudo。服务文件都在仓库的 `system/`：

| 文件 | 装到 |
|---|---|
| `system/systemd/logind-soundmat.conf` | `/etc/systemd/logind.conf.d/soundmat.conf` |
| `system/systemd/jackd.service` | `/etc/systemd/system/` |
| `system/systemd/soundmat-scsynth.service` | `/etc/systemd/system/` |
| `system/systemd/soundmat.service` | `/etc/systemd/system/` |
| `system/update/soundmat-guard` | `/usr/local/bin/`（755） |

```bash
scp system/systemd/* system/update/soundmat-guard soundmat@<主机>:/tmp/
# 在树莓派上
sudo mkdir -p /etc/systemd/logind.conf.d
sudo install -m 644 /tmp/logind-soundmat.conf /etc/systemd/logind.conf.d/soundmat.conf
sudo install -m 644 /tmp/jackd.service /tmp/soundmat-scsynth.service /tmp/soundmat.service /etc/systemd/system/
sudo install -m 755 /tmp/soundmat-guard /usr/local/bin/soundmat-guard
sudo systemctl daemon-reload && sudo systemctl restart systemd-logind
sudo systemctl enable --now jackd soundmat-scsynth
```

- `jackd.service` 里的 `hw:Audio` 是当前声卡的名字，换声卡时按 `aplay -l` 改。48 kHz、每块 2048 帧两块缓冲；Pi 5 可以看板上的卡顿次数为准逐步降到 1024、512。
- 主机程序的服务在程序装好后（第 6 节）再启用。
- Pi 3B 上程序目录不同，用 drop-in 覆盖路径：`/etc/systemd/system/soundmat.service.d/pi3b.conf` 里重设 `WorkingDirectory=/home/soundmat/sm/current`、`Environment=SOUNDMAT_HOME=/home/soundmat/sm`、`ExecStart=`（先清空）再 `ExecStart=/home/soundmat/sm/current/.venv/bin/soundmat --data-dir /home/soundmat/data`。

验证：`systemctl is-active jackd soundmat-scsynth`；`journalctl -u jackd -n 8 -o cat` 里应有 `starting in realtime mode`，**不能有** `Cannot use real-time scheduling`；`jack_lsp -c` 里 `SuperCollider:out_1/2` 接到 `system:playback_1/2`（靠服务里的 `SC_JACK_DEFAULT_OUTPUTS`，不需要 `jack_connect`）。

## 5. 网络

方案（详细设计见 `DEPLOYMENT.md`「网络」）：手机热点 `phone-hotspot`（SSID `soundmat`，优先级 100）> `uw-mpsk`（50，固定出厂 MAC）> 家里 `Avocado`（40）> 有线；都没有时自建热点 `soundmat-ap`（SSID `SoundMat-AP`，`10.42.0.1`，不自动连接），由 `soundmat-net-fallback` 每分钟检查：有更高优先级的已知网络就切过去，没网就开热点，热点开着时扫到已知网络就切回。

需要 sudo。先看现状：`nmcli -f NAME,TYPE,AUTOCONNECT,AUTOCONNECT-PRIORITY,DEVICE con show`（Imager 写入的连接名是 `netplan-wlan0-<SSID>` 或 SSID 本身）。

```bash
# 已有的连接只改优先级；没有的先不带密码建好
sudo nmcli con modify <Imager 写入的 Avocado 连接> connection.autoconnect-priority 40
sudo nmcli con add type wifi con-name phone-hotspot ifname wlan0 ssid soundmat wifi-sec.key-mgmt wpa-psk connection.autoconnect yes connection.autoconnect-priority 100
sudo nmcli con add type wifi con-name uw-mpsk ifname wlan0 ssid "UW MPSK" wifi-sec.key-mgmt wpa-psk 802-11-wireless.cloned-mac-address permanent connection.autoconnect yes connection.autoconnect-priority 50
sudo nmcli con add type wifi con-name soundmat-ap ifname wlan0 ssid SoundMat-AP mode ap 802-11-wireless.band bg 802-11-wireless.channel 6 wifi-sec.key-mgmt wpa-psk wifi-sec.proto rsn wifi-sec.pairwise ccmp wifi-sec.group ccmp wifi-sec.pmf disable ipv4.method shared ipv4.addresses 10.42.0.1/24 ipv6.method disabled connection.autoconnect no
```

已有的旧热点连接没有 `key-mgmt` 时，单独设密码会报 `key-mgmt: property is missing`，要先用 `nmcli con modify` 把上面那组加密参数补上。旧版的 `soundmat-ap-fallback.service`（只在开机时检查一次）要 `sudo systemctl disable --now`。

密码由人设置，给人这样的命令（在树莓派上提示输入，不留在历史里）：

```bash
ssh -t soundmat@<主机> 'sudo nmcli con modify phone-hotspot wifi-sec.psk soundmat && sudo nmcli con modify soundmat-ap wifi-sec.psk soundmat && echo PSK_OK'
ssh -t soundmat@<主机> 'read -s -p "Avocado 密码: " P; echo; sudo nmcli con modify <Avocado 连接> wifi-sec.psk "$P" && echo PSK_OK'
```

UW MPSK 要先用 `/sys/class/net/wlan0/address` 的 MAC 在 UW 登记，拿到密码后同样由人填。

兜底定时任务：

```bash
scp system/network/soundmat-net-fallback* soundmat@<主机>:/tmp/
sudo install -m 755 /tmp/soundmat-net-fallback /usr/local/sbin/
sudo install -m 644 /tmp/soundmat-net-fallback.service /tmp/soundmat-net-fallback.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now soundmat-net-fallback.timer
```

**测试**（改网络可能断开 SSH，不插网线时先预约回滚）：
1. 打开手机热点，一分钟内应从 Avocado 切到 `phone-hotspot`（用 Tailscale 名字确认；切换期间连接会断几秒）。
2. 预约回滚 `sudo systemd-run --on-active=8m --unit=soundmat-net-rollback nmcli con modify <Avocado 连接> connection.autoconnect yes`，再临时 `connection.autoconnect no`，关掉手机热点：NetworkManager 先重试约 80 秒，之后一分钟内出现 `SoundMat-AP`，手机连上能打开 `http://10.42.0.1:8000`。回滚生效后一分钟内切回 Avocado。
3. 看日志：`journalctl -u soundmat-net-fallback -u NetworkManager --since -15min -o short-iso | grep -E "fallback\[|state change|Activation"`。

iPhone 热点锁屏或闲置时会自己关，测试时让手机停在热点页面。

## 6. 第一次安装程序

程序以发布包的形式存在 GitHub 预发布版本里（标签 `build-<短提交号>`）。第一次在开发机上发布但不通知装置：

```bash
uv run python scripts/release.py --no-update
```

在树莓派上手工安装这个版本（`<base>` 是 `/home/soundmat/soundmat`，Pi 3B 是 `/home/soundmat/sm`）：

```bash
B=<base>; S=<短提交号>; mkdir -p $B/releases /home/soundmat/data
cd $B/releases && mkdir $S && cd $S
curl -fsSL https://github.com/mukimasta/soundmat/releases/download/build-$S/soundmat-$S.tar.gz -o /tmp/pkg.tgz
tar xzf /tmp/pkg.tgz && cat VERSION
~/.local/bin/uv sync --frozen --no-dev --quiet      # 在最终目录里建环境：.venv 写死了所在路径，不能建好再改名
touch .ready && ln -sfn releases/$S $B/current
```

然后（sudo）`sudo systemctl enable --now soundmat`。Pi 3B 上 aarch64 的 numpy 等都有现成的安装包，`uv sync` 约 7 秒；32 位系统可能没有，要先确认 `uname -m`。

在控制台把默认编排设为要拍的那一份，或者：

```bash
curl -s -X POST http://<主机>:8000/api/settings -H 'content-type: application/json' -d '{"changes": {"run.defaultArrangement": "lofi_1"}}'
curl -s -X POST http://<主机>:8000/api/arrangements/lofi_1/play
```

## 7. 日常发布与更新

在 `master` 上提交后：

```bash
uv run python scripts/release.py                              # 默认装置 soundmat-pi
uv run python scripts/release.py --device soundmat-pi-old     # Pi 3B
```

它会：检查没有未提交的改动 → 推送 → 编译音色（`instruments/` 没变就跳过）→ 构建控制台 → 打包（约 700 KB）→ 上传为 GitHub 预发布版本（保留最近 20 个）→ 用 rsync 把编排引用的素材同步到装置的 `/home/soundmat/sound/samples/`（只传有变化的；第一次约 326 MB）→ 通过 Tailscale 让装置更新 → 等装置报告新版本在运行。整个过程约 20–40 秒。`--no-sound` 跳过素材（Jam 不需要素材），`--no-update` 只发布到 GitHub。

素材的注意事项：
- 装置上的素材目录 `/home/soundmat/sound/samples` 要先存在（rsync 不建上级目录），新装的装置第一次发布前先 `ssh soundmat@<主机> mkdir -p /home/soundmat/sound/samples`。
- 大批同步（第一次约 326 MB，或新加了大素材）期间，往存储卡写入会让 Pi 3B 的音频卡顿几下（2026-10-18 实测：开始同步的 8 秒里 JACK 记了 14 次 xrun，之后为 0）。不要在演出或拍摄中做；看板的"最近一小时卡顿"提示一小时后自己消失。平时只传有变化的文件，一两秒，不受影响。

装置那边：下载、核对 SHA-256、解压到 `releases/<短提交号>/`、`uv sync`，成功后才切换 `current`，然后程序退出、由 systemd 按新版本拉起。新版本运行满 60 秒自动确认；连续 3 次启动失败，启动前运行的 `soundmat-guard` 会切回上一版。手动回退：控制台「菜单 → 软件更新 → 回到上一版」（只对本机和 Tailscale 来的访问开放），或 `curl -X POST http://<主机>:8000/api/update/rollback`。

发布命令连不上装置时，发布包已经在 GitHub 上：等装置连上后重新运行同一条命令（已上传的会跳过），或在控制台里选这个版本更新。装置正在切换网络时也会连不上，过一两分钟再试。

推送后看一眼 CI：`gh run list --repo mukimasta/soundmat --branch master --limit 3`。

## 8. 验收

逐项确认：

1. `systemctl is-active jackd soundmat-scsynth soundmat soundmat-net-fallback.timer` 全部 active。
2. 局域网 `http://soundmat-pi.local:8000`、Tailscale `http://soundmat-pi:8000` 都能打开控制台。
3. 看板一切正常：声音（USB 声卡、48 kHz、音色加载、无卡顿）、垫子（控制器已连接、传感帧率 25–30）、网络。
4. 看板「声道测试」左右各自发声。
5. 放石头：Jam 压住中间两环开始播放，外圈石头被扫描线扫到时发声，灯环上扫描线和石头位置对得上；京都岚山每环有对应的声音。核对内环方向和去抖时间（见 `TODO.md`）。
6. 断电重启：一两分钟后自动进入默认编排，看板恢复正常（开机灯带全亮 5 秒是固件的行为）。
7. 网络：第 5 节的测试。
8. 供电（Pi 5）：负载下 `vcgencmd pmic_read_adc EXT5V_V` 不低于 4.9 V，`vcgencmd get_throttled` 为 `0x0`，跑一两个小时后摸 USB 头不烫。

读整体状态的快捷方式：

```bash
curl -s http://<主机>:8000/api/state | python3 -c "
import json,sys; d=json.load(sys.stdin)['status']; t=d['timing']; m=d['machine']
print(d['program']['version'], d['current']['arrangement'], d['current']['modeStatus'])
print('health', d['health']['overall'], d['health']['issues'])
print('cpu prog', m.get('programCpu'), 'machine', m.get('cpu'), '| synth', d['audio']['synth']['avgLoad'])
print('lag', t['maxLagMs'], 'stalls', t['stallsRecent'], 'late', t['lateRecent'], '| xruns', d['audio']['xruns'])
print('rates', {k: v['actual'] for k, v in d['rates'].items()})"
```

## 9. 性能检查

看板「声音」的运算负载显示合成器和主机程序中更高的一个；「机器」里有主机程序（占单核）和整机 CPU；「节奏」里有各链路帧率和节拍延迟。按线程看主机程序（线程名已设给系统）：

```bash
ssh soundmat@<主机> 'P=$(systemctl show -p MainPID --value soundmat); top -H -b -n 1 -p $P | head -15'
```

参考（Pi 3B，所有石头摆满，Jam 播放）：主机程序约占单核 64%（声音化约 24%、灯光约 16%、主线程约 10%、设备约 7%、监测约 4%），合成器负载约 46%，节拍 60，最大节拍延迟 20–34 ms，无迟到、无卡顿。控制台开着时主线程要推送灯环和垫面，拍摄时没人看就关掉控制台的网页。测量时注意不要和安装更新撞在一起（更新时 `uv sync` 会占满一个核）。

## 10. 排错

| 现象 | 原因与处理 |
|---|---|
| 看板「垫子：控制器断开，正在重连」反复出现 | 收不到 S 帧。先确认 ESP32 通电、USB 插好；程序打开串口后会等 15 秒首帧（打开串口可能让 ESP32 复位，固件开机灯效约 5 秒不发数据）。`journalctl -u soundmat --since -2min -o cat \| grep -E "控制器\|垫子"` |
| JACK 日志 `semop (Invalid argument)`、`jack_lsp` 连不上，scsynth 服务卡在 "JACK not ready" | logind 在 soundmat 退出登录时清掉了 JACK 的信号量：装 `logind-soundmat.conf`（`RemoveIPC=no`），重启 systemd-logind，再依次重启 jackd、soundmat-scsynth |
| JACK 日志 `Cannot use real-time scheduling` | 服务缺 `LimitRTPRIO=95`（第一版就缺）：用仓库里的 `jackd.service` |
| 没声音，scsynth 在跑 | `jack_lsp -c` 看 SuperCollider 的输出有没有接到 `system:playback_*`；服务里要有 `SC_JACK_DEFAULT_OUTPUTS` |
| 看板「采样率 44.1 kHz，期望 48 kHz」 | JACK 的 `-r`。Pi 3B 用 drop-in `/etc/systemd/system/jackd.service.d/rate.conf` 重设 `ExecStart` 为 `-r48000` |
| 看板「缺少 N 个声音素材」 | 当前编排要素材（京都岚山），装置上没有：发布时不要加 `--no-sound` |
| 看板「主机程序最近一小时内被自动重启过」 | 真的在反复崩溃时：`journalctl -u soundmat -b -o cat \| grep -B2 -A20 Traceback`。更新导致的重启不算（更新时写下 `plannedAt`） |
| 看板「节拍晚到超过 50 ms」刚启动时出现 | 启动加载造成的，一分钟后消失；持续出现就看第 9 节 |
| 发布命令「连不上装置」 | Tailscale 上看 `tailscale status \| grep soundmat`；装置可能在切换网络（手机热点断了、换到 Avocado），等一两分钟重试 |
| sudo 突然又要密码 | 树莓派重启过，或超过约 15 分钟没用：请人再 `sudo -v` |
| SSH 很久没反应 | 设备离线（充电宝没电、热点关了）：`tailscale status` 看 last seen |

**Pi 3B 切回第一版**（新版出问题、来不及修时）：

```bash
ssh -t soundmat@soundmat-pi-old 'sudo systemctl disable --now soundmat soundmat-scsynth && sudo mv /etc/systemd/system/jackd.service.d/rate.conf /etc/systemd/system/jackd.service.d/rate.conf.off && sudo systemctl daemon-reload && sudo systemctl restart jackd && sudo systemctl enable --now soundmat-v1'
```

第一版自己拉起 scsynth，并按 44.1 kHz 启动，所以要先停掉 `soundmat-scsynth`，并把 JACK 恢复到原来的 44.1 kHz（第一版在 48 kHz 的 JACK 下没有验证过）。实时优先级的修正（`realtime.conf`）保留，对第一版也有好处。切回新版反过来：`disable --now soundmat-v1`，把 `rate.conf.off` 改回 `rate.conf`，`daemon-reload`、`restart jackd`，再 `enable --now soundmat-scsynth soundmat`。
