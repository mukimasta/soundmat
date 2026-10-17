// 和声铺底（移植自第一版 sc/synthdefs/jam/chord_pad.scd，对应 web 原型 harmonyPadSynth.js）。
// 一个声部 5 个音（freq0..freq4，≤ 1 的槽静音），共享包络、滤波与颤音。
// 新版中和声是持续声部：攻击层（FM）照旧自然衰减，持续层（fatsaw）靠 gate 释放（rel 1.5 秒）。
~smDef.("jam_chord_pad", {
    var freqs = [\freq0.kr(0), \freq1.kr(0), \freq2.kr(0), \freq3.kr(0), \freq4.kr(0)];
    var safeF = freqs.collect { |f| f.max(1) };
    var on = freqs.collect { |f| f > 1 };
    var gate = \gate.kr(1);
    var sEnv = EnvGen.kr(Env.adsr(0.5, 1.0, 0.6, \rel.kr(1.5), 1, [\lin, \lin, -4]), gate, doneAction: 2);
    var aEnv = EnvGen.kr(Env([0, 1, 0], [0.04, 0.8], [\lin, -4]));
    var mEnv = EnvGen.kr(Env([0, 1, 0], [0.01, 0.3], [\lin, -4]));
    var aSig = Mix.fill(5, { |i| ~jamToneFM.value(safeF[i], 3, 2.5, mEnv, aEnv) * on[i] }) * (-11).dbamp;
    var sSig = Mix.fill(5, { |i| ~jamToneFatSaw.value(safeF[i], 18) * on[i] });
    sSig = sSig * sEnv * (-7).dbamp;
    sSig = sSig * (1 + SinOsc.kr(0.6, 0, 0.015));
    sSig = ~jamLPF24.value(sSig, 1200, 0.5);
    ~smOut.((aSig + sSig) * \amp.kr(1));
});
