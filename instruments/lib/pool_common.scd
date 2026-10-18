// 冥想（网页原型 Ambient「Sound Pool」）音色共用的部分：网页的主效果链。
//
// 网页上除底音以外的声音都进同一条链：混响（Tone.Reverb，decay 7、wet 0.4）→ 8 kHz 低通 →
// 压缩器（-20 dB、2:1）→ ×0.85。这里拆开：
//   - 低通是线性的，放在混响前后等价，所以在每个声部上先做；
//   - 干声按 cos(0.4·π/2) 写到声部的总线，混响在共用效果 sm_fx_pool 里按 sin(0.4·π/2) 加回；
//   - Chrome 的压缩器（膝宽 30 dB，带自动补偿）在这么轻的电平下几乎只是 +0.8 dB：输入低于 -20 dBFS
//     时正好 +0.8，-8 dBFS 时 +0.4，接近 0 dBFS 才压到 -0.5，所以并成固定增益，和 ×0.85 一起乘在 ~poolPost 里。
// 单声道信号：网页上同时送到左右两个声道（总功率是一个声道的两倍）；引擎的空间化是等功率的，
// 所以 ×√2，定位之后的总功率仍与网页一致。立体声信号（噪声、混响）左右各自原样。
~poolDry = cos(0.4 * 0.5pi);
~poolWet = sin(0.4 * 0.5pi);
~poolPost = 0.85 * 0.8069.dbamp;

// lowpass：只有高频成分多的声音（噪声、钟声、鸟鸣）需要 8 kHz 低通；低音、和声、音符都在 2 kHz 以下，
// 这个低通对它们的影响不到 0.2 dB，省掉。
~poolOut = { |sig, lowpass = true|
    var s = (if(lowpass) { ~toneLPF.(sig, 8000, 1) } { sig }) * ~poolPost;
    if(sig.size != 2) { s = s * 2.sqrt };
    ~smOut.(s * ~poolDry, s)
};

// 持续声部的淡入淡出：网页都是线性的 rampTo
~poolGateEnv = {
    EnvGen.kr(Env.asr(\atk.kr(0.05), 1, \rel.kr(0.5), \lin), \gate.kr(1), doneAction: 2)
};

// 底音的音量起伏：±2 dB，0.015 Hz。远处的音也经过它（网页上它们汇在一起），用 phase 接上底音的相位
~poolBedVolume = { |phase = 0| SinOsc.kr(0.015, phase).range(-2.dbamp, 2.dbamp) };
~poolBedOut = 0.5;            // 网页的 bedOut：底音不经过主效果链，直接 ×0.5 输出
