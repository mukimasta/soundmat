// jam/drums/kick.scd — Kick（MembraneSynth 风格：正弦 + 音高包络）
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\jam_kick, { |amp = 1, sustain = 0.2, pan = 0, out = 6|
        var fenv = EnvGen.kr(Env.perc(0.001, 0.06, 1, -8));   // pitchDecay 0.06
        var f = 48 * (1 + (fenv * 6));                        // octaves 扫频
        var env = EnvGen.kr(Env.perc(0.001, 0.22, 1, -4), doneAction: 2);
        var sig = SinOsc.ar(f) * env * amp;
        Out.ar(out, Pan2.ar(sig, pan));
    })
);
