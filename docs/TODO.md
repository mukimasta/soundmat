# TODO

- [ ] 下周二（10-21）拍 Ambient 前：把声音素材同步到 Pi 3B（`uv run python scripts/release.py --device soundmat-pi-old`，会同步编排引用的素材），切到《京都岚山》在真垫子上试听
- [ ] 上真机核对坐标对齐：在每环放一颗石头，确认控制台垫面上的位置与实物一致。第一版的内环实际没有做扇区镜像（外环做了），新版照搬，见 `implementation/HOST_PROGRAM.md`「设备连接与垫面信号」
- [ ] 上真机调整去抖时间（`config/soundmat.toml` 的 `occupy_hold`、`release_hold`，当前是未经实测的初值）
- [ ] 查总输出电平：Pi 3B 上看板显示左声道峰值到了 −1 dBFS，正好压在总输出的限幅上；找出是哪一层偏响，或调低总音量
- [ ] 修改控制器固件：开机后保持低亮度的等待灯效，直到主机程序接管（当前固件开机 5 秒后全亮白光，5 V 总线瞬间约 3.8 A）
- [ ] 确定 SoundMat 系列文档正本的存放位置，更新 `design/SOUNDMAT_SERIES.md`
- [ ] 删除旧的 `SETUP.md`（有用内容已并入 `implementation/DEPLOYMENT.md`）
- [ ] 在 UW 为树莓派登记 UW MPSK
- [ ] Pi 3B 上新版稳定后，删除保留的第一版（`~/soundmat` 和 `soundmat-v1.service`）

### Waiting

- [ ] 在 Pi 5 上按部署 skill（`skills/soundmat-deploy/SKILL.md`）完成部署：系统服务、第一个发布包，并按 `implementation/DEPLOYMENT.md`「验收标准」逐项验证，进度记在 `implementation/DEPLOYMENT_202610.md` — 等待 USB-C 供电头（10-18 到）焊好
- [ ] 执行多石头性能评估 `evaluation/implementation/multi_stone_performance/`（Pi 3B 上的初步结果已记录） — 等待 Pi 5 部署完成
- [ ] 实测 UW MPSK：Pi 上的 `uw-mpsk` 连接已建好（优先级 50，固定出厂 MAC），尚未填密码。登记后执行 `sudo nmcli con modify uw-mpsk wifi-sec.psk <密码>`，在 UW 确认能自动连上、Tailscale 可达 — 约 2026-10-19 在 UW 测
