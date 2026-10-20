# TODO

- [ ] 上真机核对坐标对齐：在每环放一颗石头，确认控制台垫面上的位置与实物一致。第一版的内环实际没有做扇区镜像（外环做了），新版照搬，见 `implementation/HOST_PROGRAM.md`「设备连接与垫面信号」
- [ ] 上真机调整去抖时间（`config/soundmat.toml` 的 `occupy_hold`、`release_hold`，当前是未经实测的初值）
- [ ] 查控制器第一次连接总要约 20 秒：Pi 5 两次开机都是主机程序打开串口后 15 秒内收不到帧，超时断开（关闭时内核报 `cp210x ttyUSB0: failed set request 0x12 status: -110`），重开后约 4 秒连上。和欠压无关（复测时没有欠压也一样），见 `soundmat/device/__init__.py` 的 `open_serial`、`BOOT_WAIT_SECONDS`
- [ ] 修改控制器固件：开机后保持低亮度的等待灯效，直到主机程序接管（当前固件开机 5 秒后全亮白光，5 V 总线瞬间约 3.8 A）
- [ ] 确定 SoundMat 系列文档正本的存放位置，更新 `design/SOUNDMAT_SERIES.md`
- [ ] Pi 3B 上新版稳定后，删除保留的第一版（`~/soundmat` 和 `soundmat-v1.service`）
- [ ] 周二（10-20）正式录制前修复石头的感知：有时识别不到，有时抖动
- [ ] 在 Pi 3B 上试听《冥想》：对照网页原型听音色；放满石头看看板上的合成器负载（离线折算约 35%，见 `implementation/SYNTH.md`「离线渲染」）、迟到和卡顿

### Waiting

- [ ] 完成 Pi 5 的验收（`implementation/DEPLOYMENT_202610.md`「第三步」）：系统服务、发布包、素材、UW MPSK 已在 2026-10-19 完成；剩下接控制器后放石头、逐声道测试音、断电重启、自建热点兜底 — 等待把 ESP32 控制器从 Pi 3B 换到 Pi 5
- [ ] 周二（10-20）拍 Ambient 前，在 Pi 5 上切到《京都岚山》在真垫子上试听（Pi 3B 内存放不下它的素材），放满石头看输出电平：密集处峰值应在 −3 dBFS 左右，长时间贴着 −1 dB 就在编排里设 `level`（`implementation/ARRANGEMENTS.md`「共同头部」） — 等待 ESP32 控制器接到 Pi 5
- [ ] 执行多石头性能评估 `evaluation/implementation/multi_stone_performance/`（Pi 3B 上的初步结果已记录） — 等待 ESP32 控制器接到 Pi 5
