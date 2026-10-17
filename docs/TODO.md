# TODO

- [ ] 在 Mac 上试听重写后的主机程序并合并 PR（阶段 1–8，依次叠放）：编译音色、启动 scsynth、用虚拟垫子逐个检查《京都岚山》与 Lo-Fi，与第一版对比
- [ ] 上真机核对坐标对齐：在每环放一颗石头，确认控制台垫面上的位置与实物一致。第一版的内环实际没有做扇区镜像（外环做了），新版照搬，见 `implementation/HOST_PROGRAM.md`「设备连接与垫面信号」
- [ ] 上真机调整去抖时间（`config/soundmat.toml` 的 `occupy_hold`、`release_hold`，当前是未经实测的初值）
- [ ] 确定 SoundMat 系列文档正本的存放位置，更新 `design/SOUNDMAT_SERIES.md`
- [ ] 实测当前传感帧率（固件 `tools/plot_sensors.py`）
- [ ] 备份 Pi 3B 上的开机自启配置，迁移到仓库 `system/`
- [ ] 按 `implementation/DEPLOYMENT.md` 编写部署脚本 `deploy/` 和系统配置 `system/`
- [ ] 删除旧的 `SETUP.md`（有用内容已并入 `implementation/DEPLOYMENT.md`）
- [ ] 在 UW 为树莓派登记 UW MPSK
- [ ] 修改控制器固件：开机后保持低亮度的等待灯效，直到主机程序接管（当前固件开机 5 秒后全亮白光）

### Waiting

- [ ] 用一块空白存储卡在 Pi 5 上按 `implementation/DEPLOYMENT.md` 完整部署并逐项验证 — Pi 5 已到货，基础环境与网络已完成，进度见 `implementation/DEPLOYMENT_202610.md`；其余等待新版主机程序
- [ ] 执行多石头性能评估 `evaluation/implementation/multi_stone_performance/` — 等待 Pi 5 部署完成
- [ ] 实测 UW MPSK：Pi 上的 `uw-mpsk` 连接已建好（优先级 50，固定出厂 MAC），尚未填密码。登记后执行 `sudo nmcli con modify uw-mpsk wifi-sec.psk <密码>`，在 UW 确认能自动连上、Tailscale 可达 — 约 2026-10-19 在 UW 测
