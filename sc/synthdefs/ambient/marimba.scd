// ambient/marimba.scd — 马林巴原子单音（加性合成，从 sonification 迁移）
//
// \marimbaNote  敲一下就走：基频 + 4x + 10x（1:4:10），perc 包络，doneAction 自释放。
// 原子化——不内部重击；重击/随机由逻辑层调度（Ring5 随机马林巴 / Ring7 随机素材共用）。
// 时长靠 decay 控；干声 Pan2 输出。amp 单位 dB。
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\marimbaNote, { |out = 0, freq = 261.63, amp = -9, atk = 0.005, decay = 2.0, curve = -4, pan = 0|
        var sig, env;
        sig = SinOsc.ar(freq, 0, 1)
            + SinOsc.ar(freq * 4, 0, 0.3)
            + SinOsc.ar(freq * 10, 0, 0.08);
        env = EnvGen.kr(Env.perc(atk, decay, 1, curve), doneAction: 2);
        sig = sig * env * amp.dbamp;
        Out.ar(out, Pan2.ar(sig, pan));
    })
);
