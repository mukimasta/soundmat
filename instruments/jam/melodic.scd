// Jam 的旋律与贝斯音色（移植自第一版 sc/synthdefs/jam/，参数与 web 原型一致）。
// 都是单次声音：时长由 sustain 决定，包络结束后自动释放。参数 freq、velocity、ringGain、sustain。

~smDef.("jam_rhodes", {
    var freq = \freq.kr(440), velocity = \velocity.kr(1), ringGain = \ringGain.kr(1);
    var sustain = \sustain.kr(0.82), far = \far.kr(0);
    var harm = Select.kr(far, [14, 8]), mIdx = Select.kr(far, [4, 2.5]);
    var atk = Select.kr(far, [0.003, 0.008]), dec = Select.kr(far, [0.58, 0.55]);
    var susL = Select.kr(far, [0.32, 0.28]), rel = Select.kr(far, [0.85, 0.9]);
    var lpfHz = Select.kr(far, [2400, 1700]);
    var mAtk = Select.kr(far, [0.001, 0.002]), mDec = Select.kr(far, [0.08, 0.06]);
    var highDb = Select.kr(far, [-2, -4]);
    var hold = (sustain - atk - dec).max(0.01);
    var aenv = EnvGen.kr(Env([0, 1, susL, susL, 0], [atk, dec, hold, rel], [\lin, -4, \lin, -4]), doneAction: 2);
    var menv = EnvGen.kr(Env([0, 1, 0, 0, 0], [mAtk, mDec, hold, 0.45], [\lin, -4, \lin, -4]));
    var synthVol = Select.kr(far, [1, (-2).dbamp]), fmLevel = Select.kr(far, [0.11, 0.15]);
    var sig, stereo;
    sig = ~jamToneFM.value(freq, harm, mIdx, menv, aenv, fmLevel) * synthVol * velocity;
    sig = LPF.ar(sig, lpfHz);
    sig = ~jamEQ3.value(sig, 2, highDb);
    stereo = ~jamChorus2.value(sig, 0.6, 3.2, 0.55, 0.4);
    stereo = ~jamTremolo2.value(stereo[0], stereo[1], 5.2, 0.1);
    ~smOut.(stereo * 3.6 * ringGain);
});

~smDef.("jam_marimba", {
    var freq = \freq.kr(440), revSend = \revSend.kr(0.065);
    var mainEnv = ~jamToneExpDecay.value(0.012, 2.0, 2);
    var subEnv = ~jamToneExpDecay.value(0.005, 1.2, 0);
    var main, sub, wide, gain;
    main = ~jamMarimbaOsc.value(freq, mainEnv);
    main = ~jamLPF24.value(main, 1550, 0.35);
    main = ~jamVibrato.value(main, 0.3, 0.003);
    wide = ~jamWidener2.value(main, 0.48);
    sub = SinOsc.ar(freq * 0.5) * subEnv * (-22).dbamp * (freq < 262);
    gain = \velocity.kr(1) * \ringGain.kr(1) * (-5).dbamp;
    ~smOut.([(wide[0] * (1 - revSend)) + sub, (wide[1] * (1 - revSend)) + sub] * gain, wide * gain * revSend);
});

~smDef.("jam_pad_pluck", {
    var freq = \freq.kr(220), sustain = \sustain.kr(1.28);
    var aHold = (sustain - 1.23).max(0.01), fHold = (sustain - 0.62).max(0.01);
    var aenv = EnvGen.kr(Env([0, 1, 0.15, 0.15, 0], [0.03, 1.2, aHold, 0.8], [\lin, -4, \lin, -4]), doneAction: 2);
    var fenv = EnvGen.kr(Env([0, 1, 0.5, 0.5, 0], [0.02, 0.6, fHold, 0.6], [\lin, -4, \lin, -4]));
    var cutoff = ~jamFilterCutoff.value(350, 2.5, 2.5, fenv).clip(40, 16000);
    var sig = ~jamFatSaw.value(freq) * (-5).dbamp;
    sig = ~jamLPF24.value(sig, cutoff, 1.2) * aenv;
    sig = ~jamVibrato.value(sig, 4.5, 0.012);
    ~smOut.(~jamChorus2.value(sig, 0.8, 3.5, 0.6, 0.35) * \velocity.kr(1) * \ringGain.kr(1));
});

~smDef.("jam_sub_bass", {
    var env = ~jamGateReleaseEnv.value(0.015, 0.12, 0.72, 0.34, \sustain.kr(0.25), 2);
    var sig = ~jamSubOsc.value(\freq.kr(110), env);
    sig = RLPF.ar(RLPF.ar(sig, 200, 1 / 0.4), 200, 1 / 0.4);
    sig = ~jamDistWet.value(sig, 0.08, 0.4);
    sig = HPF.ar(HPF.ar(sig, 30), 30);
    ~smOut.(sig * 0.38 * \velocity.kr(1) * \ringGain.kr(1));
});

~smDef.("jam_pluck_bass", {
    var sustain = \sustain.kr(0.5);
    var aenv = ~jamGateReleaseEnv.value(0.04, 0.3, 0.28, 0.4, sustain, 2);
    var fenv = ~jamGateReleaseEnv.value(0.01, 0.2, 0.05, 0.45, sustain, 2);
    var cutoff = ~jamFilterCutoff.value(160, 2.4, 0.85, fenv).clip(40, 12000);
    var sig = Saw.ar(\freq.kr(110)) * (-10).dbamp;
    sig = RLPF.ar(sig, cutoff, 1.0) * aenv;
    sig = ~jamLPF24.value(sig, 1000, 0.45);
    sig = ~jamToneCompressor.value(sig);
    ~smOut.(sig * \velocity.kr(1) * \ringGain.kr(1));
});
