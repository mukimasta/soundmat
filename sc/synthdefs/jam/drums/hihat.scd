// jam/drums/hihat.scd — Hi-hat · NoiseSynth(-4dB) decay0.028 rel0.006 → HPF6800(-24)
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\jam_hihat, { |amp = 1, sustain = 0.03, pan = 0, out = 6|
        // sustain 参数保留 API 兼容；web 包络固定，32n/64n 只决定 gate 不关 decay 形状
        var env = EnvGen.kr(Env([0, 1, 0, 0], [0.001, 0.028, 0.006], [\lin, -4, -4]), doneAction: 2);
        var sig = WhiteNoise.ar() * env * (-4).dbamp * amp;
        sig = HPF.ar(HPF.ar(sig, 6800), 6800);
        Out.ar(out, [sig, sig]);
    })
);
