// jam/chord_pad.scd — 和声 pad · harmonyPadSynth.js
//
// hold 秒 gate（web triggerAttackRelease holdSec）→ release；不依赖外部 gate
// 攻击 FM -11dB · 持续 fatsaw spread18 -7dB → vibrato → LPF1200
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\jam_chord_pad, { |freq = 261, amp = 1, hold = 2, pan = 0, out = 4|
        var sAtk = 0.5, sDec = 1.0, sSus = 0.6, sRel = 1.5;
        var aAtk = 0.04, aDec = 0.8, aRel = 0.6;
        var mAtk = 0.01, mDec = 0.3, mRel = 0.3;
        var sHold = (hold - sAtk - sDec).max(0);
        var aHold = (hold - aAtk - aDec).max(0);
        var mHold = (hold - mAtk - mDec).max(0);
        var sEnv = EnvGen.kr(
            Env([0, 1, sSus, sSus, 0], [sAtk, sDec, sHold, sRel], [\lin, \lin, \lin, -4]),
            doneAction: 2,
        );
        var aEnv = EnvGen.kr(
            Env([0, 1, 0, 0, 0], [aAtk, aDec, aHold, aRel], [\lin, -4, \lin, -4]),
        );
        var aModEnv = EnvGen.kr(
            Env([0, 1, 0, 0, 0], [mAtk, mDec, mHold, mRel], [\lin, -4, \lin, -4]),
        );
        var aSig = ~jamToneFM.value(freq, 3, 2.5, aModEnv, aEnv) * (-11).dbamp;
        var sSig = ~jamToneFatSaw.value(freq, 18);
        var sig;
        sSig = sSig * sEnv * (-7).dbamp;
        sSig = sSig * (1 + SinOsc.kr(0.6, 0, 0.015));
        sSig = ~jamLPF24.value(sSig, 1200, 0.5);
        sig = (aSig + sSig) * amp;
        Out.ar(out, Pan2.ar(sig, pan));
    })
);
