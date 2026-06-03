// jam/chord_pad.scd — 和声 pad · harmonyPadSynth.js
//
// hold 秒 gate（web triggerAttackRelease holdSec）→ release；不依赖外部 gate
// 攻击 FM -11dB · 持续 fatsaw spread18 -7dB → vibrato → LPF1200
//
// 多频点版本：原本一个和弦 5 voice = 5 个 SynthDef 实例，每个独立 envelope/LPF/vibrato。
// 改为单实例接 freq0..freq4 5 通道，共享 envelope/LPF/vibrato，5 路 FM + 5 路 fatsaw 内部
// Mix 累加。声学等价（线性叠加，包络同步），CPU 大幅减少。freq <= 1 → 该通道静音。
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\jam_chord_pad, { |freq0 = 0, freq1 = 0, freq2 = 0, freq3 = 0, freq4 = 0,
                                amp = 1, hold = 2, pan = 0, out = 4|
        var freqs = [freq0, freq1, freq2, freq3, freq4];
        // freq <= 1 视为空槽：osc 跑一个 dummy 频率，再用 gate 清零，避免 Saw.ar(0) 的奇异行为
        var safeF = freqs.collect { |f| f.max(1) };
        var gates = freqs.collect { |f| (f > 1) };
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
        var aSig = Mix.fill(5, { |i|
            ~jamToneFM.value(safeF[i], 3, 2.5, aModEnv, aEnv) * gates[i]
        }) * (-11).dbamp;
        var sSig = Mix.fill(5, { |i|
            ~jamToneFatSaw.value(safeF[i], 18) * gates[i]
        });
        var sig;
        sSig = sSig * sEnv * (-7).dbamp;
        sSig = sSig * (1 + SinOsc.kr(0.6, 0, 0.015));
        sSig = ~jamLPF24.value(sSig, 1200, 0.5);
        sig = (aSig + sSig) * amp;
        Out.ar(out, Pan2.ar(sig, pan));
    })
);
