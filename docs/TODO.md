# TODO

- [ ] 按新架构重写主机程序（第一版已打 git 标签 `v1-ece546`；可沿用与不沿用的部分见 `implementation/MIGRATION.md`）
- [ ] 确定 SoundMat 系列文档正本的存放位置，更新 `design/SOUNDMAT_SERIES.md`
- [ ] 确认控制区与阈值参数以第 8 篇还是第一版代码为准（见 `implementation/MIGRATION.md`）
- [ ] 实测当前传感帧率（固件 `tools/plot_sensors.py`）
- [ ] 备份 Pi 3B 上的开机自启配置，迁移到仓库 `system/`
- [ ] 按 `implementation/DEPLOYMENT.md` 编写部署脚本 `deploy/` 和系统配置 `system/`
- [ ] 删除旧的 `SETUP.md`（有用内容已并入 `implementation/DEPLOYMENT.md`）
- [ ] 在 UW 为树莓派登记 UW MPSK
- [ ] 修改控制器固件：开机后保持低亮度的等待灯效，直到主机程序接管（当前固件开机 5 秒后全亮白光）

### Waiting

- [ ] 用一块空白存储卡在 Pi 5 上按 `implementation/DEPLOYMENT.md` 完整部署并逐项验证 — 等待 Pi 5 到货
- [ ] 执行多石头性能评估 `evaluation/implementation/multi_stone_performance/` — 等待 Pi 5 部署完成
