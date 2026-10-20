// 冥想：底音和远处的音（移植自网页原型 web/soundmat/src/soundmat/audio/baseLayer.js）。
// 两者都不经过主效果链，×0.5 直接输出。
(
// 底音：正弦 + 极轻的带通白噪声；低通明暗 0.02 Hz。一直在响（空垫子时也有）。
// t 是当前调相对 C 的移调倍数，换调时 0.25 秒滑过去。
// 呼吸：网页是三路相差 ±0.5 音分的正弦，拍频让音量十几秒涨落一次、深约 30 dB，这是底音听得出来的
// 起伏，但它的相位只有合成器知道，灯光跟不上。这里改成一路正弦（×3，最响时与三路同相叠加相同），
// 起伏由主机程序的呼吸值 breath（0–1，每 0.25 秒给一次，在这 0.25 秒里线性滑到它）决定：
// 最响 0 dB，最轻低 depth dB，按 dB 随呼吸值线性变化。灯光取同一个呼吸值。
~smDef.("pool_bed", {
    var t = VarLag.kr(\t.kr(1), 0.25, warp: \exponential);
    var b = VarLag.kr(\breath.kr(0.5), 0.25, warp: \linear);
    var tone = ~toneLPF.(SinOsc.ar(196.0 * t) * 3 * EnvGen.kr(Env([0, 0.035], [5])),
        SinOsc.kr(0.02).range(350 * t, 700 * t), 0.7);
    var noise = ~toneBPF.(~toneWhite.(2), 400 * t, 0.62) * (-40).dbamp;
    var sig = (tone + noise) * (\depth.kr(30) * (b - 1)).dbamp * ~poolBedOut;
    ~smOut.(sig * ~poolGateEnv.value);
});

// 远处偶尔一声正弦：0.2 秒线性淡入，6–10 秒线性淡出，进一个 decay 20、wet 0.97 的混响。
// 网页上它经过底音 ±2 dB 的音量起伏；这里跟着呼吸做同样 ±2 dB 的起伏：volPhase、volHz 是发声时
// 呼吸的相位和频率，这一声的十来秒里自己按正弦接着走。
~smDef.("pool_distant", {
    var decay = \decay.kr(8);
    var env = EnvGen.kr(Env([0.0001, \amp.kr(0.013), 0.0001], [0.2, decay]));
    var dry = SinOsc.ar(\freq.kr(220)) * env;
    var wet = ~toneReverbMono.(dry, 20);
    var sig = ([dry, dry] * ~toneDry.(0.97)) + (wet * ~toneWet.(0.97));
    Line.kr(0, 0, 0.2 + decay + 3, doneAction: 2);         // 混响尾巴再过 3 秒已低于 -45 dB
    ~smOut.(sig * SinOsc.kr(\volHz.kr(0.015), \volPhase.kr(0)).range(-2.dbamp, 2.dbamp) * ~poolBedOut);
});
)
