// jam/pluck_bass.scd — R3 · pluckBassSynth.js
//
// saw(-10dB) → filterEnv(160Hz, oct2.4, exp0.85) → ampEnv → LPF1000(Q0.45) → Comp → ringGain
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\jam_pluck_bass, { |freq = 110, velocity = 1, ringGain = 1, sustain = 0.5, pan = 0, out = 2|
        var aHold = (sustain - 0.34).max(0.02);
        var fHold = (sustain - 0.21).max(0.02);
        var aenv = EnvGen.kr(
            Env([0, 1, 0.28, 0.28, 0], [0.04, 0.3, aHold, 0.4], [\lin, -4, \lin, -4]),
            doneAction: 2,
        );
        var fenv = EnvGen.kr(Env([0, 1, 0.05, 0.05, 0], [0.01, 0.2, fHold, 0.45], [\lin, -4, \lin, -4]));
        var cutoff = ~jamFilterCutoff.value(160, 2.4, 0.85, fenv).clip(40, 12000);
        var sig = Saw.ar(freq) * (-10).dbamp;
        sig = RLPF.ar(sig, cutoff, 1 / 0.6);
        sig = sig * aenv;
        sig = ~jamLPF24.value(sig, 1000, 0.45);   // web 后级 LPF -24dB/oct Q0.45
        sig = Compander.ar(sig, sig, (-20).dbamp, 1, 1 / 3, 0.008, 0.14);
        sig = sig * velocity * ringGain;
        Out.ar(out, Pan2.ar(sig, pan));
    })
);
