// jam/chord_pad.scd — 和声 pad · harmonyPadSynth.js
//
// 攻击 FM(1:3, idx2.5) -11dB · 持续 fatsaw spread18 -7dB → vibrato → LPF1200
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\jam_chord_pad, { |freq = 261, amp = 1, hold = 2, gate = 1, pan = 0, out = 4|
        var aEnv = EnvGen.kr(Env.adsr(0.04, 0.8, 0, 0.6), gate);
        var aModEnv = EnvGen.kr(Env.adsr(0.01, 0.3, 0, 0.3), gate);
        var aSig = ~jamToneFM.value(freq, 3, 2.5, aModEnv, aEnv) * (-11).dbamp;
        var sEnv = EnvGen.kr(Env.adsr(0.5, 1.0, 0.6, 1.5), gate, doneAction: 2);
        var hc = 9;   // spread 18 cents
        var sSig = (
            Saw.ar(freq * (2 ** (hc.neg / 1200)))
            + Saw.ar(freq)
            + Saw.ar(freq * (2 ** (hc / 1200)))
        ) / 3;
        var sig;
        sSig = sSig * sEnv * (-7).dbamp;
        sSig = sSig * (1 + SinOsc.kr(0.6, 0, 0.015));
        sSig = ~jamLPF24.value(sSig, 1200, 0.5);   // web pad LPF -24dB/oct Q0.5
        sig = (aSig + sSig) * amp;
        Out.ar(out, Pan2.ar(sig, pan));
    })
);
