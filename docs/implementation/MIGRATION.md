# Migration from v1

本文写给按新架构重写主机程序的人：第一版（git 标签 `v1-ece546`，2026 年 6 月）里哪些可以直接沿用，哪些不要带过来，以及迁移时容易踩的坑。重写完成、旧代码移除后，本文可以删除或移入 `information/`。

### 第一版的结构

第一版的代码保存在 git 标签 `v1-ece546`（提交 `3803932`）。重写开始后，Python 包、测试和脚本已从工作区移除，需要时用 `git show v1-ece546:<路径>` 查看；`manifest/` 已转换为 `arrangements/` 并移除；`sc/` 和 `SETUP.md` 在对应内容迁移完成后移除。第一版的结构：

1. `soundmat/`：Python 包。`core/` 是串口、传感器、灯光、OSC 与 scsynth 管理；`jam/` 是 Jam 的五层实现；`ambient/` 是从 `sonification` 项目迁入的 Ambient；`web/` 是 FastAPI 控制台和静态网页。
2. `sc/`：SuperCollider 音色源码 `synthdefs/{core,ambient,jam}`、编译脚本 `compile.scd`、编译产物 `compiled/`；`sc/assets/samples` 是指向 `SoundMat/sound/samples` 的符号链接。
3. `manifest/`：编排数据。`ambient/kyoto.toml` 是《京都岚山》；`jam/lofi_1.toml` 引用 `jam/data/` 下的 YAML（和弦进行、旋律表、鼓组、环配置、Lo-Fi 映射）。
4. `tests/`：14 个 pytest 测试文件。
5. `SETUP.md`：第一版的部署说明，已被 `implementation/DEPLOYMENT.md` 取代。

### 可以直接沿用

1. **串口帧解析与选口规则**（`core/sensor/frame.py`、`core/esp32_serial.py`）：S 帧解析与 XOR 校验；Mac 上优先 `/dev/cu.*`，Linux 上用 `ttyUSB*` / `ttyACM*` 并排除板载串口；打开时 DTR、RTS 置低，避免 USB 串口芯片把 ESP32 复位；ESP32 开机灯效约 5 秒期间不发 S 帧，要等到第一帧 `S:` 再开始发送灯光帧。
2. **坐标映射规则**（`core/sensor/map.py`、`core/sensor/normalize.py`，以及测试 `test_sensor_map.py`、`test_wire_normalize.py`）：固件发出 8 × 32 的接线矩阵；扇区方向需要镜像（slice s 对应 31 − s）才与实物顺时针一致；内两环只有一半的 slice 有效，镜像后有效数据落在奇数 slice 上；整体再旋转 4 个扇区。新架构里这些规则属于垫面信号的"坐标对齐"，并要映射到 `system_design/DATA_MODEL.md` 的 224 区域模型（内两环每环 16 区）。部署时校准过的偏移值（扇区偏移 4、灯带偏移 101、镜像开启）写进配置文件。
3. **Jam 的音乐逻辑**（`jam/theory/`、`jam/scheduler/`、`jam/event/`，以及对应测试）：简谱记号解析、按调与音阶换算音高、节拍方案、和弦位置、鼓组曲式、扫描命中与八分量化。新架构下它们成为 Jam 模式的内部实现，输出改为声音意图；扫描命中需要改为在前瞻时间窗内计算准确时刻。
4. **Jam 灯光**（`jam/led/layers.py`、`jam/led/renderer.py`）：系列文档第 8 篇 Jam 灯光方案的实现，可改写为 Jam 模式的灯光层。
5. **Jam 与 Ambient 的编排数据**：`manifest/` 下的内容转换为新的编排格式（TOML，见 `implementation/TECH_STACK.md`）。Jam 的 YAML 需要转换格式。
6. **音色**（`sc/synthdefs/`）：移到 `instruments/`。`jam/00_common.scd` 定义了其他 Jam 音色共用的函数，编译时必须先加载。旧音色输出固定的立体声并写死了总线编号，要改为输出到声音引擎分配的多声道环总线。
7. **网络脚本**（`SoundMat/system/pi/setup-soundmat-network.sh`）：用 NetworkManager 先连手机热点、60 秒后未联网则开自建热点，并设置 avahi。已于 2026-10-17 由 `system/network/soundmat-net-fallback` 取代：改为定期检查，并在已知网络回来时自动切回；连接配置见 `DEPLOYMENT.md`「网络」一节。热点密码按 `DECISION.md` 第 6 条直接写进文档。
8. **性能调优结论**：系列文档第 16 篇的 JACK 缓冲与 scsynth 块大小设置，以及和弦铺底合并为一个声部的做法。其余旧优化不要预先带入，见 `DECISION.md` 第 4 条。

### 不要带过来

1. 用全局变量保存运行时参数（新架构由状态中心管理并持久保存）。
2. 串口打不开时悄悄改用虚拟输入（新架构必须由系统监测明确报告）。
3. 虚拟输入在接线坐标上注入，并临时关闭镜像来对齐（新架构的虚拟垫子从压力图接入）。
4. Jam 和 Ambient 各自做阈值判断（新架构由感知统一判断）。
5. 不带时间戳、立即执行的 OSC 指令。
6. 由 Python 启动 scsynth 子进程、写死 `-o 2` 立体声输出。
7. 灯光在各模式的主循环里以每秒 20 或 30 次合成。
8. 网页控制台 `web/static/mat.html`（新控制台按 `design/CONSOLE.md` 重写）。

### 需要注意的事实

1. **校准与控制区参数以第一版代码为准**（2026-10-16 与 Human 确认）：单区阈值 500、控制区启动阈值 250、Lo-Fi 在控制区压力和 1000 到 8000 之间映射、旋律声部上限 12、扇区偏移 4、灯带偏移 101、扇区镜像开启。这些都是原始 ADC 读数（12 位，满量程 4095），新版作为固定值写进配置文件和 Jam 编排，不再在控制台调整。系列文档第 8 篇写的"压力和达到 1000 时 Lo-Fi 最大"已过时。
2. **声音素材格式**：`SoundMat/sound/samples` 中是 48 kHz、24 位的 WAV（扩展格式），Python 标准库的 `wave` 读不了，需要用 soundfile 一类的库。
3. **主机名不一致**：第一版的样本同步脚本 `scripts/sync_samples_to_pi.sh`（未提交）连接 `soundmat-pi.local`，而旧网络脚本把主机名设为 `soundmat`。新部署统一使用 `soundmat-pi`（见 `DEPLOYMENT.md`，Pi 5 已按此部署）。控制台显示运行时的实际主机名。
4. **固件开机灯效**：当前固件开机先半亮白光 5 秒，再全亮白光，直到收到第一帧灯光数据。架构要求改为低亮度等待，固件尚未修改。
