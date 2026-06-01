// jam/drums/snare.scd — Snare · Tone NoiseSynth（白噪声 decay 0.12）
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\jam_snare, { |amp = 1, sustain = 0.12, pan = 0, out = 6|
        var env = EnvGen.kr(Env.perc(0.001, 0.12, 1, -4), doneAction: 2);
        var sig = WhiteNoise.ar() * env * amp * 0.75;
        Out.ar(out, [sig, sig]);
    })
);
