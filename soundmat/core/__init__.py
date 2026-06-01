"""共享底层服务：scsynth 进程、OSC、传感器读取、LED 输出。

两个模式（jam/ambient）共用这一套硬件 I/O 与 SC 服务器；模式各自的音乐逻辑在自己的
包里独立发展。`SharedServices` 把这些服务打包传给模式 app。
"""
