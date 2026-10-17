// 素材回放（移植自第一版 sc/synthdefs/core/players.scd）。
// 声道数在编译时固定，所以单声道、立体声分开；需要保时长变调（semitones）时用 _tune 变体。
// 持续声部 loop = 1，靠 gate 淡出；单次声音 loop = 0，放完自动释放。
// 干声写到环总线，按 revSend 发送到共用混响。参数：amp（dB）、rate、rateVar、lpf、hpf、revSend。

[1, 2].do { |chans|
    [false, true].do { |tune|
        var name = "sm_play_" ++ (if(chans == 1) { "mono" } { "stereo" }) ++ (if(tune) { "_tune" } { "" });
        ~smDef.(name, {
            var buf = \buf.kr(0), loop = \loop.kr(1), rate = \rate.kr(1), rateVar = \rateVar.kr(0);
            var r = rate * (2 ** (Rand(rateVar.neg, rateVar) / 12));
            var sig = PlayBuf.ar(chans, buf, r * BufRateScale.kr(buf), startPos: \startPos.kr(0), loop: loop);
            FreeSelfWhenDone.kr(sig);
            if(tune) { sig = PitchShift.ar(sig, \winSize.kr(0.2), 2 ** (\semitones.kr(0) / 12), 0, 0.004) };
            sig = sig * ~smGateEnv.value * \amp.kr(0).dbamp;
            sig = LPF.ar(HPF.ar(sig, \hpf.kr(20)), \lpf.kr(20000));
            ~smOut.(sig, sig * \revSend.kr(0));
        });
    };
};
