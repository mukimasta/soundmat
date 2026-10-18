// 混音结构（system_design/SOUND_ENGINE.md「混音结构」）。
//
// 每个模式实例：各环总线与分组总线（最多 12 条，in0..in11，未用的指向一条静音总线）按各自增益
// gain0..gain11 相加，加上共用效果的返回（fxIn × fxGain），经过模式总处理（Lo-Fi：cutoff、drive、
// lofiGain），再乘编排电平（mixGain，按 mixFade 秒过渡；切换编排时旧的一组在这里淡出），写到总输出总线。
// 各输入的电平以 10 次/秒用 /sm_peak 回报（replyID = 输入序号），供控制台的每环电平使用。
// 录制分轨：每条输入（乘过总线增益和编排电平、未经模式总处理）另外加到 stem0..stem11 指定的
// 全局分轨总线上，效果返回加到 stemFx；切换编排时新旧两个实例一起汇入，分轨不中断。未用的指向一条废弃总线。
(
var maxIn = 12;
~smDef.("sm_mode", {
    var n = ~numCh;
    var cutoffIn = \cutoff.kr(20000);
    var cutoff = cutoffIn.clip(60, 18000).lag(0.02);     // 与第一版相同上限 18 kHz，更高会接近奈奎斯特而失稳
    var drive = \drive.kr(0);
    var xfade = VarLag.kr(\mixGain.kr(0), \mixFade.kr(0));
    var fx = In.ar(\fxIn.kr(0), n) * \fxGain.kr(1);
    var sig = maxIn.collect { |i|
        var s = In.ar(NamedControl.kr(("in" ++ i).asSymbol, 0), n) * NamedControl.kr(("gain" ++ i).asSymbol, 1, 0.05);
        SendPeakRMS.kr(s, 10, 3, '/sm_peak', i);
        Out.ar(NamedControl.kr(("stem" ++ i).asSymbol, 0), s * xfade);
        s
    }.sum;
    Out.ar(\stemFx.kr(0), fx * xfade);
    sig = sig + fx;
    // cutoff ≥ 18 kHz（默认值）时不经过低通
    sig = Select.ar(cutoffIn >= 18000, [RLPF.ar(RLPF.ar(sig, cutoff, 1.389), cutoff, 1.389), sig]);
    sig = ~jamDistWet.value(sig, drive, (drive / 0.025).clip(0, 1));
    sig = sig * \lofiGain.kr(1).lag(0.02) * xfade;
    Out.ar(\out.kr(0), sig);
});

// 共用效果：FreeVerb，每个声道一个（Ambient，第一版 core/reverb.scd：room 0.85、damp 0.3）
~smDef.("sm_fx_freeverb", {
    var sig = In.ar(\in.kr(0), ~numCh);
    sig = sig.collect { |ch| FreeVerb.ar(ch, 1.0, \room.kr(0.85), \damp.kr(0.3)) };
    Out.ar(\out.kr(0), sig * \amp.kr(0).dbamp);
});

// 共用效果：第一版 Jam 的 Schroeder 混响（decay 1.4、preDelay 0.02），按声道两两成对处理
~smDef.("sm_fx_jam", {
    var sig = In.ar(\in.kr(0), ~numCh);
    var out = (0, 2 .. ~numCh - 1).collect { |i|
        ~jamToneReverb2.value(sig[i], sig[i + 1], 1.0, \decay.kr(1.4), \preDelay.kr(0.02))
    }.flatten;
    Out.ar(\out.kr(0), out * \amp.kr(1));
});

// 共用效果：冥想的主混响（网页 Tone.Reverb decay 7、wet 0.4），每个声道一个、互不相关。
// 干声已经由声部按 cos 写到各自的总线（instruments/lib/pool_common.scd），这里只加回湿声。
~smDef.("sm_fx_pool", {
    var sig = In.ar(\in.kr(0), ~numCh);
    Out.ar(\out.kr(0), ~toneReverb.(sig.asArray, 7) * ~poolWet * \amp.kr(1));
});

// 总输出：系统音量、限幅（-1 dB），写到硬件输出 0..N-1；输出电平用 /sm_peak 回报（replyID 100）
~smDef.("sm_master", {
    var sig = In.ar(\in.kr(0), ~numCh) * \volume.kr(0.8).lag(0.1);
    sig = Limiter.ar(sig, \ceiling.kr(-1).dbamp, 0.01);
    SendPeakRMS.kr(sig, 10, 3, '/sm_peak', 100);
    Out.ar(0, sig);
});

// 逐声道测试音：直接写到某个硬件声道，确认每只音箱接对了位置
~smDef.("sm_test_tone", {
    var env = EnvGen.kr(Env.linen(0.02, \dur.kr(1.0), 0.1), doneAction: 2);
    Out.ar(\channel.kr(0), SinOsc.ar(\freq.kr(440)) * env * \amp.kr(0.2));
});
)
