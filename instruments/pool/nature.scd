// 冥想：天气和自然（移植自网页原型 web/soundmat/src/soundmat/audio/ 的 weatherVoice、natureVoice）。
// 都经过网页的主效果链（~poolOut），不定位；噪声是立体声（左右独立），和网页一样。
(
// 天气：风（粉红噪声，带通 200–1800 Hz 与高通 800–3000 Hz 各自慢慢移动）和雨（粉红噪声，带通
// 2200–3800 Hz 漂移、6.4 kHz 低通）。石头数决定风、雨各占多少（windMix、rain），变化时 1.5 秒过渡；
// 雨变大时主机程序每 0.25 秒给一次渐入曲线上的值（rainTime 0.25），在这段时间里线性滑过去。
// 主机程序给出阵风（wind 在 windTime 秒内线性到达）和雷声时雨声的加强（boost、boostTime）。
// 持续声部。
~smDef.("pool_weather", {
    var windPink = ~tonePink.(2, 1.55);
    var windBand = ~toneBPF.(windPink, SinOsc.kr(0.01).range(200, 1800), 0.7);
    var windHigh = ~toneHPF.(windPink, SinOsc.kr(0.007).range(800, 3000), 1) * 0.3;
    var windGain = VarLag.kr(\wind.kr(0.03), \windTime.kr(4), warp: \linear, start: 0)
        + SinOsc.kr(0.008).range(0.01, 0.05);
    var wind = (windBand + windHigh) * windGain * VarLag.kr(\windMix.kr(1), 1.5, warp: \linear);
    var rainBand = ~toneBPF.(~tonePink.(2, 1.68), SinOsc.kr(\driftPeriod.kr(63).reciprocal).range(2200, 3800), 0.82);
    var rainGain = SinOsc.kr(\rainPeriod.kr(75).reciprocal).range(0.008, 0.036)
        * VarLag.kr(\rain.kr(0), \rainTime.kr(1.5), warp: \linear)
        * VarLag.kr(\boost.kr(1), \boostTime.kr(0.5), warp: \linear);
    var rain = ~toneLPF.(rainBand, 6400, 0.55) * rainGain;
    ~poolOut.((wind + rain) * ~poolGateEnv.value);
});

// 雷声：褐噪声的低频滚雷（低通从 fStart 指数升到 fEnd，像雷在靠近）+ 粉红噪声的中频"空气感"；
// 包络指数起音 tAtk 秒、保持 sus 秒、线性衰减 tRel 秒。
~smDef.("pool_thunder", {
    var atk = \tAtk.kr(0.5), sus = \sus.kr(2), rel = \tRel.kr(8);
    var cutoff = EnvGen.kr(Env([\fStart.kr(90), \fEnd.kr(470)], [atk + (0.55 * sus)], \exp));
    var rumble = ~toneLPF.(~toneBrown.(~toneWhite.(2)), cutoff, 1.1);
    var air = ~toneBPF.(~tonePink.(2, 1.57), \airFreq.kr(1000), 0.72) * \airGain.kr(0.33);
    var peak = \amp.kr(0.53);
    var env = EnvGen.ar(Env([0.0001, peak, peak, 0.0001], [atk, sus, rel], [\exp, \lin, \lin]), doneAction: 2);
    ~poolOut.((rumble + air) * env);
});

// 水滴：正弦 20 ms 内从 freq 滑到 freq − 200，3 ms 指数起音，decay 秒指数衰减；
// 先进一个 decay 11、wet 0.86 的混响，再进主效果链。
~smDef.("pool_drop", {
    var f0 = \freq.kr(1000), decay = \decay.kr(1.5), peak = \amp.kr(0.075);
    var env = EnvGen.ar(Env([0.0001, peak, peak, 0.0001], [0.003, 0.021, decay], \exp));
    var dry = SinOsc.ar(EnvGen.ar(Env([f0, f0 - 200], [0.02])));
    var wet = ~toneReverbMono.(dry * env, 11);
    Line.kr(0, 0, 0.024 + decay + 2.5, doneAction: 2);     // 混响尾巴再过 2.5 秒已低于 -45 dB
    ~poolOut.(([dry, dry] * env * ~toneDry.(0.86)) + (wet * ~toneWet.(0.86)), false);
});

// 鸟鸣的一声啾：正弦从 f0 线性升到 f1（up 秒）再降到 f2（到 dur 秒），8 ms 指数起音，
// 然后 decay 秒指数衰减。几声怎样组合（一问一答、两只、一串）由主机程序决定。
~smDef.("pool_chirp", {
    var dur = \dur.kr(0.2), up = \up.kr(0.1), decay = \decay.kr(0.18);
    var freq = EnvGen.ar(Env([\f0.kr(2000), \f1.kr(3400), \f2.kr(2200)], [up, (dur - up).max(0.001)]));
    var env = EnvGen.ar(Env([0.0001, \amp.kr(0.2), 0.0001], [0.008, decay], \exp), doneAction: 2);
    var sig = SinOsc.ar(freq) * env;
    ~poolOut.([sig, sig]);
});
)
