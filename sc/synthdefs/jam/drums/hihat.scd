// jam/drums/hihat.scd — Hi-hat · NoiseSynth(-4dB) → HPF6800(-24,Q0.85)
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\jam_hihat, { |amp = 1, sustain = 0.03, pan = 0, out = 6|
        var env = EnvGen.kr(Env.perc(0.001, sustain.max(0.005), 1, -6), doneAction: 2);
        var sig = WhiteNoise.ar() * env * (-4).dbamp * amp;
        sig = HPF.ar(HPF.ar(sig, 6800), 6800);
        Out.ar(out, Pan2.ar(sig, pan));
    })
);
