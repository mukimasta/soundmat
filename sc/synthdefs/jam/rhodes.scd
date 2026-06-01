// jam/rhodes.scd — R5/R6 · rhodesSynth.js
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\jam_rhodes, { |freq = 440, velocity = 1, ringGain = 1, sustain = 0.82, pan = 0, far = 0, out = 2|
        var harm = Select.kr(far, [14, 8]);
        var mIdx = Select.kr(far, [4, 2.5]);
        var atk = Select.kr(far, [0.003, 0.008]);
        var dec = Select.kr(far, [0.58, 0.55]);
        var susL = Select.kr(far, [0.32, 0.28]);
        var rel = Select.kr(far, [0.85, 0.9]);
        var lpfHz = Select.kr(far, [2400, 1700]);
        var mAtk = Select.kr(far, [0.001, 0.002]);
        var mDec = Select.kr(far, [0.08, 0.06]);
        var highDb = Select.kr(far, [-2, -4]);
        var hold = (sustain - atk - dec).max(0.01);
        // SC \exp 曲线端点不能为 0；用数值曲率 -4（指数形状，零安全）
        var aenv = EnvGen.kr(
            Env([0, 1, susL, susL, 0], [atk, dec, hold, rel], [\lin, -4, \lin, -4]),
            doneAction: 2,
        );
        var menv = EnvGen.kr(Env([0, 1, 0], [mAtk, mDec], [\lin, -4]));
        var synthVol = Select.kr(far, [1, (-2).dbamp]);
        // FM 电平补偿已收进 ~jamToneFM（~jamToneFMLevel）；这里照抄 web makeup 3.6 即可。
        var sig, stereo, makeup;
        sig = ~jamToneFM.value(freq, harm, mIdx, menv, aenv) * synthVol;
        sig = LPF.ar(sig, lpfHz);
        sig = ~jamEQ3.value(sig, 2, highDb);
        stereo = ~jamChorus2.value(sig, 0.6, 3.2, 0.55, 0.4);
        stereo = ~jamTremolo2.value(stereo[0], stereo[1], 5.2, 0.1);
        makeup = 3.6 * velocity * ringGain;
        Out.ar(out, Balance2.ar(stereo[0], stereo[1], pan) * makeup);
    })
);
