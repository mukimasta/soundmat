// 冥想：底音和远处的音（移植自网页原型 web/soundmat/src/soundmat/audio/baseLayer.js）。
// 两者都不经过主效果链：网页上它们汇到一起，经过 ±2 dB 的音量起伏，×0.5 直接输出。
(
// 底音：三路相差 ±0.5 音分的正弦（拍频周期十几秒）+ 极轻的带通白噪声；低通明暗 0.02 Hz。
// 一直在响（空垫子时也有）。t 是当前调相对 C 的移调倍数，换调时 0.25 秒滑过去。
~smDef.("pool_bed", {
    var t = VarLag.kr(\t.kr(1), 0.25, warp: \exponential);
    var root = 196.0 * t;
    var sines = [-0.5, 0, 0.5].collect { |cents| SinOsc.ar(root * (2 ** (cents / 1200))) }.sum;
    var tone = ~toneLPF.(sines * EnvGen.kr(Env([0, 0.035], [5])), SinOsc.kr(0.02).range(350 * t, 700 * t), 0.7);
    var noise = ~toneBPF.(~toneWhite.(2), 400 * t, 0.62) * (-40).dbamp;
    var sig = (tone + noise) * ~poolBedVolume.value * ~poolBedOut;
    ~smOut.(sig * ~poolGateEnv.value);
});

// 远处偶尔一声正弦：0.2 秒线性淡入，6–10 秒线性淡出，进一个 decay 20、wet 0.97 的混响。
// volPhase：发声时底音音量起伏的相位，让它也跟着同一个起伏走。
~smDef.("pool_distant", {
    var decay = \decay.kr(8);
    var env = EnvGen.kr(Env([0.0001, \amp.kr(0.013), 0.0001], [0.2, decay]));
    var dry = SinOsc.ar(\freq.kr(220)) * env;
    var wet = ~toneReverbMono.(dry, 20);
    var sig = ([dry, dry] * ~toneDry.(0.97)) + (wet * ~toneWet.(0.97));
    Line.kr(0, 0, 0.2 + decay + 3, doneAction: 2);         // 混响尾巴再过 3 秒已低于 -45 dB
    ~smOut.(sig * ~poolBedVolume.(\volPhase.kr(0)) * ~poolBedOut);
});
)
