// 马林巴单音（加性合成 1:4:10，移植自第一版 sc/synthdefs/ambient/marimba.scd）。敲一下就结束，时长靠 decay。
~smDef.("marimbaNote", {
    var freq = \freq.kr(261.63);
    var sig = SinOsc.ar(freq) + SinOsc.ar(freq * 4, 0, 0.3) + SinOsc.ar(freq * 10, 0, 0.08);
    var env = EnvGen.kr(Env.perc(\atk.kr(0.005), \decay.kr(2.0), 1, \curve.kr(-4)), doneAction: 2);
    sig = sig * env * \amp.kr(-9).dbamp;
    ~smOut.(sig, sig * \revSend.kr(0));
});
