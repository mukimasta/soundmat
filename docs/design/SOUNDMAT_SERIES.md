# SoundMat Series

树莓派主机系统的对象设计（装置应该怎样表现）不在本仓库里重写，而是以 SoundMat 系列文档为准。本文说明这些资料在哪里、哪几篇与主机系统有关。

### 本仓库在 SoundMat 总文件夹中的位置

本仓库位于 `SoundMat/system/pi/soundmat/`。`SoundMat/` 总文件夹本身不是 git 仓库，其中与本仓库相关的部分有：

1. `SoundMat/system/firmware/soundmat_firmware/`：控制器固件（独立 git 仓库），工具 `tools/plot_sensors.py` 可以实测传感帧率。
2. `SoundMat/system/sensor/`、`SoundMat/system/electronics/`：传感器图案设计工具，电路与元件清单。
3. `SoundMat/sound/`：声音素材库，包括原始录音 `raw/`、处理好的样本 `samples/` 和转换工具 `tools/`。本仓库旧代码中的 `sc/assets/samples` 是指向 `sound/samples` 的符号链接。
4. `SoundMat/web/soundmat/`：浏览器版原型（独立 git 仓库，React + Tone.js），Jam 的节拍、和声、鼓组与灯光方案最早在这里实现。
5. `SoundMat/submissions/`：比赛与课程材料，其中 GYDC 2026 的叙事要求见下文。

### 系列文档

系列文档共 18 篇，目前有两份：Claude 上名为 SoundMat 的 Project 中的版本，以及 `SoundMat/submissions/ee546_presentation/docs/` 下 2026 年 6 月的快照。哪一份作为正本尚未确定（见 `TODO.md`）。

与主机系统直接相关的几篇：

1. **第 2 篇《Philosophy 产品设计哲学》**：公共艺术装置的定位、好装置的五个条件、用户场景。
2. **第 5 篇《传感器原理及设计》**：8 环、内两环 16 区、外六环 32 区，共 224 个感应区；扫描原理与串扰。
3. **第 6 篇《电子系统设计》**：电源、ESP32、USB 声卡、灯带的连接方式。
4. **第 7 篇《固件设计》**：S 帧、L 帧的串口协议。
5. **第 8 篇《交互与声音化设计》**：Ambient《京都岚山》的分环编排、Jam 的节拍方案、和声、触发表、鼓组和灯光方案。这是声音化的主要依据。
6. **第 16 篇《软件部署性能优化》**：第一版在树莓派上的优化记录。文中写的"Pi 4"有误，实际是 Pi 3B。

第 12 篇《软件设计与开发》描述的是第一版的软件设计，已不作为现行设计，见 `DECISION.md`。

### GYDC 的 Expression 要求

`SoundMat/submissions/GYDC/02-叙事/expression.md` 定义了作品要表达什么，并列出对作品的五条要求：挪动一下必须有效果、变的是整体而不是多一层、声音充满空间、结果不是事先写死的一一对应、状态会带着之前的痕迹留下来。架构中的空间化和可插拔特征主要为前三条准备。
