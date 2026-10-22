# TODO

- [ ] 在每环放一颗石头，确认控制台上的位置和灯光与实物一致（内外环同一角度已在 2026-10-20 实测对齐，见 `DECISION.md` 第 13 条）
- [ ] 完成 Pi 5 的验收（`implementation/DEPLOYMENT_202610.md`「第三步」）：剩下逐声道测试音、关掉手机热点后重启看自建热点能否接上、在局域网里打开 `http://soundmat-pi.local:8000`、看板三项逐项核对
- [ ] 在真垫子上验证石头跟踪（`evaluation/system_design/stone_tracking/EVALUATION.md`「待验证」）：骑线、挨着放、拖过环缝和中心、同一根导电条上放重石头；用 `scripts/replay_mat.py` 回放新录音对照
- [ ] 修第 6 区（135°）断掉的扇区导电条，或在配置里把它标为失效
- [ ] 修改控制器固件：开机后保持低亮度的等待灯效，直到主机程序接管（当前固件开机 5 秒后全亮白光，5 V 总线瞬间约 3.8 A）
- [ ] 确定 SoundMat 系列文档正本的存放位置，更新 `design/SOUNDMAT_SERIES.md`
- [ ] Pi 3B 上新版稳定后，删除保留的第一版（`~/soundmat` 和 `soundmat-v1.service`）
- [ ] 在真垫子上、透过毛毡、在暗室里调《冥想》的灯光（编排的 `[light]`、`[breath]`，默认值只是起点）：看灯和底音的涌起落下是否对得上、接近全暗时会不会一级一级跳；明显时考虑 gamma 校正
- [ ] 在 Pi 3B 上试听《冥想》：对照网页原型听音色；放满石头看看板上的合成器负载（离线折算约 35%，见 `implementation/SYNTH.md`「离线渲染」）、迟到和卡顿
- [ ] 在 Pi 5 上用真垫子试听《京都岚山》（Pi 3B 内存放不下它的素材），放满石头看输出电平：密集处峰值应在 −3 dBFS 左右，长时间贴着 −1 dB 就在编排里设 `level`（`implementation/ARRANGEMENTS.md`「共同头部」）
- [ ] 执行多石头性能评估 `evaluation/implementation/multi_stone_performance/`（Pi 3B 上的初步结果已记录）
