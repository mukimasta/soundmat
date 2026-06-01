// jam/pluck_bass.scd — R3 · pluckBassSynth.js
//
// gate = sustain 参数 → amp/filter 包络 + release
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\jam_pluck_bass, { |freq = 110, velocity = 1, ringGain = 1, sustain = 0.5, pan = 0, out = 2|
        var aAtk = 0.04, aDec = 0.3, aSus = 0.28, aRel = 0.4;
        var fAtk = 0.01, fDec = 0.2, fSus = 0.05, fRel = 0.45;
        var aenv = ~jamGateReleaseEnv.value(aAtk, aDec, aSus, aRel, sustain, 2);
        var fenv = ~jamGateReleaseEnv.value(fAtk, fDec, fSus, fRel, sustain, 2);
        var cutoff = ~jamFilterCutoff.value(160, 2.4, 0.85, fenv).clip(40, 12000);
        var sig = Saw.ar(freq) * (-10).dbamp;
        sig = RLPF.ar(sig, cutoff, 1 / 1.0);
        sig = sig * aenv;
        sig = ~jamLPF24.value(sig, 1000, 0.45);
        sig = ~jamToneCompressor.value(sig);
        sig = sig * velocity * ringGain;
        Out.ar(out, [sig, sig]);
    })
);
