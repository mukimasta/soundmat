// 录制（docs/design/RECORDING.md）：scsynth 在内部把总线写成文件，没有环境噪声。

// 把一条 N 声道总线写进一个已用 /b_write 打开的缓冲区（DiskOut 流式写盘）。
// 总输出从硬件输出总线 0 读取（sm_master 已在同一周期写入），分轨从全局分轨总线读取。
~smDef.("sm_rec", {
    DiskOut.ar(\buf.kr(0), In.ar(\in.kr(0), ~numCh));
});

// 打板提示音：1 kHz、80 毫秒的短音，均匀写到总输出总线，经过系统音量送到音箱，也进入总输出录音。
~smDef.("sm_slate", {
    var env = EnvGen.kr(Env([0, 1, 1, 0], [0.003, 0.074, 0.003]), doneAction: 2);
    var sig = SinOsc.ar(1000) * env * \amp.kr(-12).dbamp;
    Out.ar(\out.kr(0), sig ! ~numCh / ~numCh.sqrt);
});
