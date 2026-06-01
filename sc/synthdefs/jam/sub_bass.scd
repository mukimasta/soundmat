// jam/sub_bass.scd — R2 · subBassSynth.js
//
// partials → LPF(200,-24,Q0.4) → Distortion(wet0.4,drive0.08) → HPF(30,-12) → amp0.3 → ringGain
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\jam_sub_bass, { |freq = 110, velocity = 1, ringGain = 1, sustain = 0.25, pan = 0, out = 2|
        var atk = 0.015, dec = 0.12, susL = 0.72, rel = 0.34;
        var hold = (sustain - atk - dec).max(0.02);
        // \exp 端点不能为 0，用数值曲率 -4
        var env = EnvGen.kr(
            Env([0, 1, susL, susL, 0], [atk, dec, hold, rel], [\lin, -4, \lin, -4]),
            doneAction: 2,
        );
        var sig = ~jamSubOsc.value(freq, env);
        sig = RLPF.ar(RLPF.ar(sig, 200, 1 / 0.4), 200, 1 / 0.4);
        sig = ~jamDistWet.value(sig, 0.08, 0.4);
        sig = HPF.ar(sig, 30);
        sig = sig * 0.3 * velocity * ringGain;
        Out.ar(out, Pan2.ar(sig, pan));
    })
);
