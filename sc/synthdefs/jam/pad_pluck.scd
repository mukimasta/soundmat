// jam/pad_pluck.scd — R4 · padPluckSynth.js
//
// chain: osc → filter → ampEnv → Vibrato → Chorus（web 同序）
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\jam_pad_pluck, { |freq = 220, velocity = 1, ringGain = 1, sustain = 1.28, pan = 0, out = 2|
        var aHold = (sustain - 1.23).max(0.01);
        var fHold = (sustain - 0.62).max(0.01);
        var aenv = EnvGen.kr(
            Env([0, 1, 0.15, 0.15, 0], [0.03, 1.2, aHold, 0.8], [\lin, -4, \lin, -4]),
            doneAction: 2,
        );
        var fenv = EnvGen.kr(Env([0, 1, 0.5, 0.5, 0], [0.02, 0.6, fHold, 0.6], [\lin, -4, \lin, -4]));
        var cutoff = ~jamFilterCutoff.value(350, 2.5, 2.5, fenv).clip(40, 16000);
        var sig = ~jamFatSaw.value(freq) * (-5).dbamp;
        var stereo, gain;
        sig = ~jamLPF24.value(sig, cutoff, 1.2);
        sig = sig * aenv;
        sig = ~jamVibrato.value(sig, 4.5, 0.012);
        stereo = ~jamChorus2.value(sig, 0.8, 3.5, 0.6, 0.35);
        gain = velocity * ringGain;
        Out.ar(out, Balance2.ar(stereo[0], stereo[1], pan) * gain);
    })
);
