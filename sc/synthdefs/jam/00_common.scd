// jam/00_common.scd — Web Tone.js 对齐 helper（jam/synths/*.js 参数为唯一真源）
//
// 加载顺序：compile.scd 递归 load 时本文件应最先（00_ 前缀）。
~synthDefs = ~synthDefs ? [];

// Tone FMSynth（ModulationSynth）：freq_inst = fc + sin(2π·fc·h·t) · modIndex · fc · modEnv
//
// 关键：SC 正弦 FM 输出是满幅(±1)，而 Tone FMSynth "运行很轻"（web rhodes 注释亦言此，
// 故需 makeup 3.6）。实测 Tone FMSynth 有效电平 ≈ 本 SC 实现的 0.22×。把这个引擎差异
// 收敛到此处统一补偿，所有 FMSynth 调用（rhodes / chord_pad 攻击层）自动一致，调用方
// 只需照抄 web 的 makeup / -11dB 等参数即可，无需各自再 fudge。
~jamToneFMLevel = 0.22;
~jamToneFM = { |freq, harmonicity = 3, modIndex = 2.5, modEnv = 1, ampEnv = 1, level = 0.22|
    var mod = SinOsc.ar(freq * harmonicity) * modIndex * freq * modEnv;
    SinOsc.ar(freq + mod) * ampEnv * level;
};

// Tone fatsaw count:3 spread:cents — 三路 saw 直接相加，不除以 count
~jamToneFatSaw = { |freq, spreadCents = 18|
    var hc = spreadCents * 0.5;
    Saw.ar(freq * (2 ** (hc.neg / 1200)))
    + Saw.ar(freq)
    + Saw.ar(freq * (2 ** (hc / 1200)))
};

// Tone.Compressor(threshold -20, ratio 3, knee 8) · Compander 无 knee 会压过头，后接 makeup
~jamToneCompressor = { |sig, threshold = -20, ratio = 3, attack = 0.008, release = 0.14|
    Compander.ar(sig, sig, threshold.dbamp, 1, 1 / ratio, attack, release) * (4.5).dbamp
};

// Tone FilterEnvelope: base * 2^(octaves * env^exponent)
~jamFilterCutoff = { |base, octaves, exponent, fenv|
    base * (2 ** (octaves * fenv.clip(0, 1).pow(exponent)));
};

// Tone Filter rolloff:-24 = 两级同 Q biquad 级联（Tone 对所有级用同一 Q）。
// 单级 RLPF 只有 -12dB/oct，高次泛音漏过 → 音色偏亮"生"；这里统一成 -24。
~jamLPF24 = { |sig, freq, q = 0.707|
    var rq = 1 / q;
    RLPF.ar(RLPF.ar(sig, freq, rq), freq, rq);
};

// Tone triggerAttackRelease(gate) + release
~jamGateReleaseEnv = { |attack, decay, susLevel, release, gate, done=2|
    var hold = (gate - attack - decay).max(0);
    EnvGen.kr(
        Env([0, 1, susLevel, susLevel, 0], [attack, decay, hold, release], [\lin, -4, \lin, -4]),
        doneAction: done,
    );
};

// Tone Chorus（spread 180° = 正交 LFO）
~jamChorus2 = { |sig, rate = 0.6, delayMs = 3.2, depth = 0.55, wet = 0.4|
    var del0 = delayMs * 0.001;
    var dep = depth * 0.001 * 0.5;
    var lfoL = SinOsc.kr(rate);
    var lfoR = SinOsc.kr(rate, pi * 0.5);
    var wetL = DelayC.ar(sig, 0.05, del0 + (lfoL * dep));
    var wetR = DelayC.ar(sig, 0.05, del0 + (lfoR * dep));
    [
        (sig * (1 - wet)) + (wetL * wet),
        (sig * (1 - wet)) + (wetR * wet),
    ]
};

// Tone Tremolo spread 180°
~jamTremolo2 = { |l, r, rate = 5.2, depth = 0.1|
    var tL = 1 - (depth * 0.5 * (1 - SinOsc.kr(rate)));
    var tR = 1 - (depth * 0.5 * (1 - SinOsc.kr(rate, pi * 0.5)));
    [l * tL, r * tR]
};

// Tone EQ3（Rhodes: low +2 @250, high -2/-4 @2500）
~jamEQ3 = { |sig, lowDb = 2, highDb = -2|
    var s = BLowShelf.ar(sig, 250, 1, lowDb);
    BHiShelf.ar(s, 2500, 1, highDb)
};

// Tone StereoWidener width 0..1
~jamWidener2 = { |sig, width = 0.48|
    var d1 = DelayC.ar(sig, 0.03, 0.011);
    var d2 = DelayC.ar(sig, 0.03, 0.009);
    var side = (d1 - d2) * width;
    var mid = sig;
    [mid + side, mid - side]
};

// Tone Distortion waveshaper（Distortion.ts 曲线；amount = web distortion 0..1）
~jamToneDistort = { |sig, amount = 0|
    var deg = pi / 180;
    var a = amount.max(0);
    ((3 + a) * sig * 20 * deg) / (pi + (a * sig.abs));
};

// Tone Distortion wet mix（Sub sat: drive 0.08 wet 0.4）
~jamDistWet = { |sig, drive = 0.08, wet = 0.4|
    var sat = ~jamToneDistort.value(sig, drive);
    (sig * (1 - wet)) + (sat * wet)
};

// Tone Vibrato：depth 是 NormalRange 0–1（pad 0.012 = 1.2%），不是秒
// delay-time LFO；depth 1.0 ≈ ±10ms 延迟摆动
~jamVibrato = { |sig, rate = 0.3, depth = 0.003|
    var maxDev = 0.01;
    var center = 0.005;
    var mod = SinOsc.kr(rate) * depth * maxDev;
    DelayC.ar(sig, 0.02, (center + mod).clip(0.0001, 0.0199));
};

// Marimba partials [1,0,0,0.14,0,0,0,0,0,0.02] — 1-indexed harmonics
~jamMarimbaOsc = { |freq, env = 1|
    var amps = [1.0, 0, 0, 0.14, 0, 0, 0, 0, 0, 0.02];
    Mix.fill(10, { |i| SinOsc.ar(freq * (i + 1)) * amps[i] }) * env
};

// Sub partials [1, 0.08, 0.025]
~jamSubOsc = { |freq, env = 1|
    (
        SinOsc.ar(freq)
        + (SinOsc.ar(freq * 2) * 0.08)
        + (SinOsc.ar(freq * 3) * 0.025)
    ) * env
};

// Tone Synth decayCurve:"exponential" — 端点用 0.001 避 SC \exp 粘零
~jamToneExpDecay = { |attack, decay, done=2|
    EnvGen.kr(Env([0, 1, 0.001], [attack, decay], [\lin, \exp]), doneAction: done);
};

// Tone.Reverb(decay1.4, preDelay0.02, wet0.08) — Schroeder + 湿声 HF 衰减（卷积 IR 高频掉更快）
~jamToneReverb2 = { |l, r, wet = 0.08, decaySec = 1.4, preDelay = 0.02|
    var inL = DelayC.ar(l, 0.05, preDelay);
    var inR = DelayC.ar(r, 0.05, preDelay + 0.0008);
    var mono = (inL + inR) * 0.5;
    var t60 = decaySec * 0.82;
    var scale = t60 / 1.4;
    var dts = [0.0297, 0.0371, 0.0411, 0.0437] * scale;
    var combL = Mix.fill(4, { |i|
        CombC.ar(mono, 0.2, dts[i], t60)
    }) * 0.25;
    var combR = Mix.fill(4, { |i|
        CombC.ar(mono, 0.2, dts[i] * 1.07, t60 * 0.97)
    }) * 0.25;
    var apL = combL, apR = combR;
    [0.005, 0.0017, 0.0113].do { |dt|
        apL = AllpassC.ar(apL, 0.05, dt * scale, t60 * 0.45);
        apR = AllpassC.ar(apR, 0.05, (dt * 1.11) * scale, t60 * 0.42);
    };
    apL = LPF.ar(apL, 5200);
    apR = LPF.ar(apR, 5200);
    [
        (l * (1 - wet)) + (apL * wet),
        (r * (1 - wet)) + (apR * wet),
    ]
};

// 3-voice fatsaw spread cents
~jamFatSaw = { |freq|
    var hc = 7; // spread 14 cents → ±7
    (
        Saw.ar(freq * (2 ** (hc.neg / 1200)))
        + Saw.ar(freq)
        + Saw.ar(freq * (2 ** (hc / 1200)))
    ) / 3
};
