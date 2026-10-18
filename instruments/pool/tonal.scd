// 冥想：有音高的声音（移植自网页原型 web/soundmat/src/soundmat/audio/ 的 droneVoice、padVoice、
// eventsVoice）。都经过网页的主效果链（~poolOut），跟着石头的方位。
(
// 低音：正弦 + 高 1.5 音分的三角波（pool_drone_tri，第 0 环）或锯齿波（pool_drone_saw，第 1 环）×0.2；
// 低通在 lfoLo–lfoHi 之间慢慢明暗（lfoPeriod 秒一周），正弦的音高 ±40 音分漂移（driftPeriod 秒一周）。
// 持续声部。
// SC 的 Saw 比 Web Audio 的锯齿波低 4.6 dB（实测各次谐波一致），×1.70 对齐；三角波一致。
[\pool_drone_tri, { |f| LFTri.ar(f) }, \pool_drone_saw, { |f| Saw.ar(f) * 1.70 }].pairsDo { |name, second|
    ~smDef.(name, {
        var freq = \freq.kr(65.41);
        var drift = SinOsc.kr(\driftPeriod.kr(240).reciprocal).range(-40, 40);
        var sig = SinOsc.ar(freq * (2 ** (drift / 1200))) + (second.(freq * (2 ** (1.5 / 1200))) * 0.2);
        var cutoff = SinOsc.kr(\lfoPeriod.kr(160).reciprocal).range(\lfoLo.kr(120), \lfoHi.kr(300));
        sig = ~toneLPF.(sig, cutoff, 1) * \amp.kr(0.1) * ~poolGateEnv.value;
        ~poolOut.(sig, false);
    });
};

// 和声：一颗石头一个声部，主机程序每隔几秒让它起一个正弦长音（noteAtk 秒线性淡入，从起音算起
// hold 秒后用 fall 秒线性淡出），几个音此起彼伏。起音由参数 n 的变化触发，音高和包络同时给出；
// 5 个音位轮流使用（间隔至少 4 秒，一个音最长 18 秒）。持续声部，gate 置 0 时整体淡出。
~smDef.("pool_pad", {
    var slots = 5;
    var n = \n.kr(0);
    var trig = Changed.kr(n) + Impulse.kr(0);
    var notes = slots.collect { |i|
        var t = trig * BinaryOpUGen('==', n % slots, i);
        var atk = Latch.kr(\noteAtk.kr(3), t);
        var hold = Latch.kr(\hold.kr(9), t);
        var env = EnvGen.kr(Env([0, 1, 1, 0], [atk, (hold - atk).max(0), Latch.kr(\fall.kr(4.5), t)]), t);
        SinOsc.ar(Latch.kr(\freq.kr(261.63), t)) * env
    }.sum;
    var cutoff = SinOsc.kr(\lfoPeriod.kr(120).reciprocal).range(\lfoLo.kr(800), \lfoHi.kr(1200));
    var sig = ~toneLPF.(notes, cutoff, 1) * \noteAmp.kr(0.03) * \amp.kr(0.6) * ~poolGateEnv.value;
    ~poolOut.(sig, false);
});

// 钟声：非谐波的五个分音（1、2、3、4.2、5.4 倍），高的分音衰减得快；指数衰减到 0.0001。
~smDef.("pool_bell", {
    var freq = \freq.kr(523.25), decay = \decay.kr(14);
    var ratios = [1, 2, 3, 4.2, 5.4];
    var levels = [1, 0.48, 0.34, 0.22, 0.16].normalizeSum;
    var decays = [1, 0.35, 0.2, 0.11, 0.06];
    var sig = ratios.collect { |r, i|
        SinOsc.ar(freq * r) * EnvGen.kr(Env([levels[i], 0.0001], [decay * decays[i]], \exp))
    }.sum;
    Line.kr(0, 0, decay, doneAction: 2);
    ~poolOut.(sig * \amp.kr(0.04));
});

// 音符：正弦（高音符）或三角波（中音符），noteAtk 秒线性起音，停 0.1 秒，decay 秒线性衰减。
// pool_note_echo 加网页高音符的回声：FeedbackDelay 0.8 秒、反馈 0.3、wet 0.35，而且原声另外还
// 直接送出一份（网页把包络同时接到回声和输出上），所以原声是 1 + cos、回声是 sin。
// 分成两个音色，没有回声的不必分配 0.8 秒的延迟缓冲。
[\pool_note, false, \pool_note_echo, true].pairsDo { |name, echo|
    ~smDef.(name, {
        var freq = \freq.kr(440), atk = \noteAtk.kr(0.005), decay = \decay.kr(3);
        var env = EnvGen.kr(Env([0, 1, 1, 0], [atk, 0.1, decay]));
        var sig = Select.ar(\tri.kr(0), [SinOsc.ar(freq), LFTri.ar(freq)]) * env * \amp.kr(0.03);
        if(echo) {
            var delayed = CombN.ar(sig, 0.81, 0.8, 0.8 * log(0.001) / log(0.3));
            sig = (sig * (1 + ~toneDry.(0.35))) + (delayed * ~toneWet.(0.35));
        };
        Line.kr(0, 0, atk + 0.1 + decay + (if(echo) { 5 } { 0 }), doneAction: 2);
        ~poolOut.(sig, false);
    });
};
)
