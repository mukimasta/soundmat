// jam/marimba.scd — R7 · marimbaSynth.js
//
// chain: osc → LPF → Vibrato → Widener → Reverb（web 同序）
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\jam_marimba, { |freq = 440, velocity = 1, ringGain = 1, sustain = 2.012, pan = 0, out = 2|
        var mainEnv = ~jamToneExpDecay.value(0.012, 2.0, 2);
        var subEnv = ~jamToneExpDecay.value(0.005, 1.2, 0);
        var main, sub, wide, dryWet, gain;
        main = ~jamMarimbaOsc.value(freq, mainEnv);
        main = ~jamLPF24.value(main, 1550, 0.35);
        main = ~jamVibrato.value(main, 0.3, 0.003);
        wide = ~jamWidener2.value(main, 0.48);
        dryWet = ~jamToneReverb2.value(wide[0], wide[1], 0.065, 1.4, 0.02);
        sub = SinOsc.ar(freq * 0.5) * subEnv * (-22).dbamp * (freq < 262);
        gain = velocity * ringGain * (-5).dbamp;
        Out.ar(out, Balance2.ar(dryWet[0] + sub, dryWet[1] + sub, pan) * gain);
    })
);
