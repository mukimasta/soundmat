// 网页原型（Tone.js / Web Audio）里几样基本构件在 SC 里的对应实现，供移植过来的音色使用。
// 对齐的依据是 Tone.js 15 和 Chrome 的 Web Audio 源码，不是听感：同样的参数得到同样的声音。

// ── 滤波器：Web Audio 的 BiquadFilterNode ─────────────────────────────────────
// 系数按 Web Audio 规范（与 Chrome 一致）计算，用 SOS 实现。注意 Web Audio 里低通、高通的 Q
// 是分贝（共振峰高出多少 dB），带通的 Q 才是通常的线性 Q。Tone.Filter 的 Q 默认是 1。
~toneBiquad = { |sig, b0, b1, b2, a0, a1, a2|
    SOS.ar(sig, b0 / a0, b1 / a0, b2 / a0, a1.neg / a0, a2.neg / a0)
};

~toneW0 = { |freq| 2pi * freq.max(10).min(SampleRate.ir * 0.49) / SampleRate.ir };

~toneLPF = { |sig, freq, qDb = 1|
    var w0 = ~toneW0.(freq), cosw = cos(w0);
    var alpha = sin(w0) / (2 * (10 ** (qDb / 20)));
    var b = (1 - cosw) / 2;
    ~toneBiquad.(sig, b, 2 * b, b, 1 + alpha, -2 * cosw, 1 - alpha)
};

~toneHPF = { |sig, freq, qDb = 1|
    var w0 = ~toneW0.(freq), cosw = cos(w0);
    var alpha = sin(w0) / (2 * (10 ** (qDb / 20)));
    var b = (1 + cosw) / 2;
    ~toneBiquad.(sig, b, (1 + cosw).neg, b, 1 + alpha, -2 * cosw, 1 - alpha)
};

~toneBPF = { |sig, freq, q = 1|
    var w0 = ~toneW0.(freq), cosw = cos(w0);
    var alpha = sin(w0) / (2 * q);
    ~toneBiquad.(sig, alpha, 0, alpha.neg, 1 + alpha, -2 * cosw, 1 - alpha)
};

// ── 噪声：Tone.Noise 的三种颜色 ───────────────────────────────────────────────
// Tone 的噪声是预先算好的立体声缓冲（左右独立），这里对每个声道的白噪声做同样的运算。
// 白噪声：均匀分布 [-1, 1)，与 Math.random() * 2 - 1 相同。
~toneWhite = { |channels = 2| WhiteNoise.ar(1 ! channels) };

// 粉红噪声：Tone 用 Paul Kellet 的方法（六个一阶滤波器相加，×0.11），照抄要十几个 UGen；这里用 SC 自带的
// PinkNoise（一个 UGen），频谱略陡一点、电平低一些：实测 1/3 倍频程能量比 Tone 的在 200 Hz 低 3.3 dB、
// 1 kHz 低 3.8 dB、3 kHz 低 4.3 dB、6 kHz 低 4.8 dB，所以按用到的频段乘上 gain（例如风 1.55、雨 1.68），
// 误差在 ±0.5 dB 以内。
~tonePink = { |channels = 2, gain = 1.58| PinkNoise.ar(gain ! channels) };

// 褐色噪声：Tone 的 (上一个 + 0.02 × 白) / 1.02，×3.5（实际是截止约 150 Hz 的一阶低通）
~toneBrown = { |white| FOS.ar(white, 0.02 / 1.02, 0, 1 / 1.02) * 3.5 };

// ── 干湿：Tone.Effect 的 wet 是等功率交叉（CrossFade）─────────────────────────
~toneDry = { |wet| cos(wet * 0.5pi) };
~toneWet = { |wet| sin(wet * 0.5pi) };

// ── 混响：Tone.Reverb ─────────────────────────────────────────────────────────
// Tone.Reverb 的冲激响应是指数衰减的白噪声：预延迟 10 ms 之后从满幅开始，时间常数
// ln(decay + 1) / ln(200) 秒（decay 7 时约 0.39 秒，衰减 60 dB 约 2.7 秒），左右声道各一段独立的
// 噪声；Web Audio 的卷积再按冲激响应的均方根归一化，所以每个声道的能量是
// (10^(-58/20) × 44100 / 48000)² × (decay + 0.01) × 48000，只和缓冲长度有关。
//
// 这里不做卷积（在 Pi 3B 上太贵），用 FreeVerb2（不加阻尼），按这两点对齐：
//   - 衰减：FreeVerb 回馈 = 0.7 + 0.28 × room，实测 48 kHz 下衰减 60 dB 的时间
//     ≈ 3 × 0.03038 / −log10(回馈)；
//   - 能量：一路输入时，每个输出声道在 100 Hz–6 kHz 的平均能量响应实测 ≈ 0.054 / (1 − 回馈²)。
//     按可闻的频段对齐，因为 FreeVerb 的频谱在 12 kHz 以上弱一些，按全频带算会让中频偏强。
//     测冲激响应时冲激不能放在第 0 个采样：FreeVerb 初始化时先把第一个采样算一遍，会算两次。
// 对单一频率，两种混响的响应都随频率随机起伏（实测标准差 5.5 dB 对 5.2 dB），统计上一致。
// 只在 48 kHz 下校准过（FreeVerb 的延迟是固定的采样数）。
~toneReverbRoom = { |decay|
    var tau = log(decay + 1) / log(200);
    var fb = 10 ** (-3 * 0.03038 / (tau * log(1000)));
    var energy = ((-58).dbamp * 44100 / 48000).squared * (decay + 0.01) * 48000;
    [(fb - 0.7) / 0.28, (energy * (1 - fb.squared) / 0.054).sqrt]    // [room, 输出增益]
};

// 单声道信号进、立体声出（远处的音、水滴各自的混响）：左右各 4 个梳状滤波器并联、再串 3 个全通，
// 延迟和 FreeVerb 错开。水滴的混响后面还要进主混响，两级如果都用 FreeVerb，共振峰落在同样的频率上、
// 互相放大（实测平均响几 dB，不同音高之间起伏也大得多）；网页上两段混响是互不相关的噪声。
// 梳状滤波器的衰减直接给 60 dB 衰减时间；能量 = Σ 1 / (1 − g²)（g 是每圈的增益），全通不改变能量。
~toneReverbMonoDelays = [[29.7, 37.1, 41.1, 43.7], [31.3, 35.9, 39.7, 46.3]] * 0.001;
~toneReverbMonoAllpass = [[5.0, 1.7, 3.9], [4.3, 2.3, 3.1]] * 0.001;
~toneReverbMono = { |sig, decay = 7|
    var tau = log(decay + 1) / log(200);
    var t60 = tau * log(1000);
    var energy = ((-58).dbamp * 44100 / 48000).squared * (decay + 0.01) * 48000;
    ~toneReverbMonoDelays.collect { |delays, ch|
        var raw = delays.collect { |d| (1 - (0.001 ** (2 * d / t60))).reciprocal }.sum;
        var s = delays.collect { |d| CombN.ar(sig, d, d, t60) }.sum;
        ~toneReverbMonoAllpass[ch].do { |d| s = AllpassN.ar(s, d, d, d * 19.37) };   // 增益 0.7
        s * (energy / raw).sqrt
    }
};

// 多声道进、多声道出：每个声道单独混响（网页的卷积也是左进左出、右进右出），所以左右不相关的声音
// （噪声）、偏向一侧的声音，混响的能量都和网页一致。相邻声道轮流用 FreeVerb2 的左、右两个混响，
// 互不相关；多于两只音箱时，隔一个声道的两路结构相同。
~toneReverb = { |chans, decay = 7|
    var rg = ~toneReverbRoom.(decay);
    chans.collect { |ch, i| FreeVerb2.ar(ch, DC.ar(0), 1, rg[0], 0)[i % 2] * rg[1] }
};
