// jam/marimba.scd — R7 · marimbaSynth.js
//
// chain: osc → LPF → Vibrato → Widener → (dry → out) + (wet → revBus 共享 reverb)
//
// 旧版 inline reverb（wet=0.065）按每路 voice 算一份 reverb，密集扫描时 N 路马林巴 = N 份 reverb。
// 现改成 send/return：dry 路径不变；湿声以 revSend(=老 wet=0.065) 送 JAM_REVERB_BUS，
// 由 \jam_reverb_bus 单实例 reverb 处理后加回 MELODY_BUS。听感等价，CPU 从 ×N 变 ×1。
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\jam_marimba, { |freq = 440, velocity = 1, ringGain = 1, sustain = 2.012, pan = 0,
                              revBus = 10, revSend = 0.065, out = 2|
        var mainEnv = ~jamToneExpDecay.value(0.012, 2.0, 2);
        var subEnv = ~jamToneExpDecay.value(0.005, 1.2, 0);
        var main, sub, wide, gain, dryMul, dryL, dryR;
        main = ~jamMarimbaOsc.value(freq, mainEnv);
        main = ~jamLPF24.value(main, 1550, 0.35);
        main = ~jamVibrato.value(main, 0.3, 0.003);
        wide = ~jamWidener2.value(main, 0.48);
        sub = SinOsc.ar(freq * 0.5) * subEnv * (-22).dbamp * (freq < 262);
        gain = velocity * ringGain * (-5).dbamp;
        // 与旧 inline reverb 等能量：dry 部分 ×(1 - revSend)，reverb 输入再用 revSend 比例送
        dryMul = 1 - revSend;
        dryL = (wide[0] * dryMul) + sub;
        dryR = (wide[1] * dryMul) + sub;
        Out.ar(out, Balance2.ar(dryL, dryR, pan) * gain);
        // 共享 reverb 由 send 量决定湿声权重；reverb 是线性，pre/post 乘等价
        Out.ar(revBus, [wide[0], wide[1]] * gain * revSend);
    })
);
