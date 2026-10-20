// 冥想：底音和远处的音（移植自网页原型 web/soundmat/src/soundmat/audio/baseLayer.js）。
// 两者都不经过主效果链：网页上它们汇到一起，经过 ±2 dB 的音量起伏，×0.5 直接输出。
(
// 底音：三路相差 ±0.5 音分的正弦（拍频周期十几秒）+ 极轻的带通白噪声；低通明暗 0.02 Hz。
// 一直在响（空垫子时也有）。t 是当前调相对 C 的移调倍数，换调时 0.25 秒滑过去。
// breath 是主机程序每 0.25 秒给一次的呼吸值（0–1），在这 0.25 秒里线性滑到它。
// 测量：正弦部分（拍频、低通、淡入、呼吸都在内，不含噪声）的振幅，以三路同相、呼吸最高时为 1，
// 每秒 20 次送回主机程序（/sm_report），冥想的灯光跟着它明暗。只测量，不改变输出。
~smDef.("pool_bed", {
    var t = VarLag.kr(\t.kr(1), 0.25, warp: \exponential);
    var root = 196.0 * t;
    var sines = [-0.5, 0, 0.5].collect { |cents| SinOsc.ar(root * (2 ** (cents / 1200))) }.sum;
    var tone = ~toneLPF.(sines * EnvGen.kr(Env([0, 0.035], [5])), SinOsc.kr(0.02).range(350 * t, 700 * t), 0.7);
    var noise = ~toneBPF.(~toneWhite.(2), 400 * t, 0.62) * (-40).dbamp;
    var gain = ~poolBreathGain.(VarLag.kr(\breath.kr(0.5), 0.25, warp: \linear));
    var sig = (tone + noise) * gain * ~poolBedOut;
    var level = Amplitude.kr(tone * gain, 0.05, 0.2) / (3 * 0.035 * \depth.kr(2).dbamp);
    SendReply.kr(Impulse.kr(20), '/sm_report', level);
    ~smOut.(sig * ~poolGateEnv.value);
});

// 远处偶尔一声正弦：0.2 秒线性淡入，6–10 秒线性淡出，进一个 decay 20、wet 0.97 的混响。
// volPhase、volHz：发声时呼吸的相位和频率，这一声的十来秒里自己按正弦接着走，跟上底音的起伏。
~smDef.("pool_distant", {
    var decay = \decay.kr(8);
    var env = EnvGen.kr(Env([0.0001, \amp.kr(0.013), 0.0001], [0.2, decay]));
    var dry = SinOsc.ar(\freq.kr(220)) * env;
    var wet = ~toneReverbMono.(dry, 20);
    var sig = ([dry, dry] * ~toneDry.(0.97)) + (wet * ~toneWet.(0.97));
    Line.kr(0, 0, 0.2 + decay + 3, doneAction: 2);         // 混响尾巴再过 3 秒已低于 -45 dB
    ~smOut.(sig * ~poolBreathGain.(SinOsc.kr(\volHz.kr(0.015), \volPhase.kr(0)) * 0.5 + 0.5) * ~poolBedOut);
});
)
