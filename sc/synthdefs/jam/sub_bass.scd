// jam/sub_bass.scd — R2 · subBassSynth.js
//
// gate = sustain 参数（web triggerAttackRelease 时长）→ 之后 release 0.34
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\jam_sub_bass, { |freq = 110, velocity = 1, ringGain = 1, sustain = 0.25, pan = 0, out = 2|
        var atk = 0.015, dec = 0.12, susL = 0.72, rel = 0.34;
        var env = ~jamGateReleaseEnv.value(atk, dec, susL, rel, sustain, 2);
        var sig = ~jamSubOsc.value(freq, env);
        sig = RLPF.ar(RLPF.ar(sig, 200, 1 / 0.4), 200, 1 / 0.4);
        sig = ~jamDistWet.value(sig, 0.08, 0.4);
        sig = HPF.ar(HPF.ar(sig, 30), 30);
        sig = sig * 0.38 * velocity * ringGain;
        Out.ar(out, [sig, sig]);
    })
);
