// jam/marimba.scd — R7 · marimbaSynth.js
//
// main: partials → LPF(-24,Q0.35) → Vibrato → Widener → Reverb(wet0.08) → -5dB
// sub: sine/2 dry → outGain（不过 LPF/vibrato/widener/reverb）
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\jam_marimba, { |freq = 440, velocity = 1, ringGain = 1, sustain = 2.012, pan = 0, out = 2|
        // sustain 0 的 AD 衰减：用 perc（曲线 -4，零安全），对应 Tone decay 2.0 + release 0.35
        var mainEnv = EnvGen.kr(Env.perc(0.012, 2.0, 1, -4), doneAction: 2);
        var subEnv = EnvGen.kr(Env.perc(0.005, 1.2, 1, -4));
        var vib = SinOsc.kr(0.3, 0, 0.003);
        var f = freq * (1 + vib);
        var main, sub, wide, rev, dryWet, gain;
        main = ~jamMarimbaOsc.value(f, mainEnv);
        main = ~jamLPF24.value(main, 1550, 0.35);   // web -24dB/oct Q0.35
        wide = ~jamWidener2.value(main, 0.48);
        rev = FreeVerb2.ar(wide[0], wide[1], 1.0, 0.55, 0.35);
        dryWet = [wide[0], wide[1]] * 0.92 + (rev * 0.08);
        sub = SinOsc.ar(f * 0.5) * subEnv * (-22).dbamp * (freq < 262);
        gain = velocity * ringGain * (-5).dbamp;
        Out.ar(out, Balance2.ar(dryWet[0] + sub, dryWet[1] + sub, pan) * gain);
    })
);
