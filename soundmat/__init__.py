"""SoundMat 上位机软件包。

公共艺术装置：圆形垫面放石头 → 实时生成音乐。两种模式：
- Jam：节拍驱动的 Lo-Fi 循环（旋转扫描触发旋律/bass，固定循环和声/鼓）。
- Ambient：氛围环境音乐（《京都岚山》主题）。

数据流：ESP32 --串口--> Pi(Python 逻辑) --OSC--> scsynth --USB DAC--> 音响
                                  └--串口 L 帧--> ESP32 --> LED 灯带
"""

__version__ = "0.1.0"
