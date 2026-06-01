// players.scd — 采样回放 SynthDef（ambient 用；从 sonification 迁移）
//
// 声道数编译期固定，故 mono/stereo 分开；Python 端按 buf.num_channels 自动选。
//   \playStereo / \playMono            普通回放
//   \playStereoTune / \playMonoTune    保时长变调（PitchShift，多 semitones/winSize）
// 单次 vs 持续靠 loop：loop=0 播完 FreeSelfWhenDone 自释放；loop=1 靠 gate=0 包络淡出。
// 通用旋钮：amp(dB) rate rateVar startPos atk/rel loop gate lpf/hpf out revBus/revSend
//   playStereo 多 width；playMono 多 pan。
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\playStereo, { |buf = 0, amp = 0.0, rate = 1.0, rateVar = 0.0,
        startPos = 0, atk = 0.01, rel = 0.5, loop = 1, gate = 1,
        width = 1.0, lpf = 20000, hpf = 20, out = 0, revBus = 0, revSend = 0.0|
        var sig, env, r, mid, side;
        r = rate * (2 ** (Rand(rateVar.neg, rateVar) / 12));
        sig = PlayBuf.ar(2, buf, r * BufRateScale.kr(buf), startPos: startPos, loop: loop, doneAction: 0);
        FreeSelfWhenDone.kr(sig);
        env = EnvGen.kr(Env.asr(atk, 1, rel, \sin), gate, doneAction: 2);
        sig = sig * env * amp.dbamp;
        sig = LPF.ar(HPF.ar(sig, hpf), lpf);
        mid = (sig[0] + sig[1]) * 0.5;
        side = (sig[0] - sig[1]) * 0.5 * width;
        sig = [mid + side, mid - side];
        Out.ar(out, sig);
        Out.ar(revBus, sig * revSend);
    })
);

~synthDefs = ~synthDefs.add(
    SynthDef(\playMono, { |buf = 0, amp = 0.0, rate = 1.0, rateVar = 0.0,
        startPos = 0, atk = 0.01, rel = 0.5, loop = 1, gate = 1,
        pan = 0.0, lpf = 20000, hpf = 20, out = 0, revBus = 0, revSend = 0.0|
        var sig, env, r;
        r = rate * (2 ** (Rand(rateVar.neg, rateVar) / 12));
        sig = PlayBuf.ar(1, buf, r * BufRateScale.kr(buf), startPos: startPos, loop: loop, doneAction: 0);
        FreeSelfWhenDone.kr(sig);
        env = EnvGen.kr(Env.asr(atk, 1, rel, \sin), gate, doneAction: 2);
        sig = sig * env * amp.dbamp;
        sig = LPF.ar(HPF.ar(sig, hpf), lpf);
        sig = Pan2.ar(sig, pan);
        Out.ar(out, sig);
        Out.ar(revBus, sig * revSend);
    })
);

~synthDefs = ~synthDefs.add(
    SynthDef(\playMonoTune, { |buf = 0, amp = 0.0, rate = 1.0, rateVar = 0.0,
        semitones = 0.0, winSize = 0.2,
        startPos = 0, atk = 0.01, rel = 0.5, loop = 1, gate = 1,
        pan = 0.0, lpf = 20000, hpf = 20, out = 0, revBus = 0, revSend = 0.0|
        var sig, env, r;
        r = rate * (2 ** (Rand(rateVar.neg, rateVar) / 12));
        sig = PlayBuf.ar(1, buf, r * BufRateScale.kr(buf), startPos: startPos, loop: loop, doneAction: 0);
        FreeSelfWhenDone.kr(sig);
        sig = PitchShift.ar(sig, winSize, 2 ** (semitones / 12), 0, 0.004);
        env = EnvGen.kr(Env.asr(atk, 1, rel, \sin), gate, doneAction: 2);
        sig = sig * env * amp.dbamp;
        sig = LPF.ar(HPF.ar(sig, hpf), lpf);
        sig = Pan2.ar(sig, pan);
        Out.ar(out, sig);
        Out.ar(revBus, sig * revSend);
    })
);

~synthDefs = ~synthDefs.add(
    SynthDef(\playStereoTune, { |buf = 0, amp = 0.0, rate = 1.0, rateVar = 0.0,
        semitones = 0.0, winSize = 0.2,
        startPos = 0, atk = 0.01, rel = 0.5, loop = 1, gate = 1,
        width = 1.0, lpf = 20000, hpf = 20, out = 0, revBus = 0, revSend = 0.0|
        var sig, env, r, mid, side;
        r = rate * (2 ** (Rand(rateVar.neg, rateVar) / 12));
        sig = PlayBuf.ar(2, buf, r * BufRateScale.kr(buf), startPos: startPos, loop: loop, doneAction: 0);
        FreeSelfWhenDone.kr(sig);
        sig = PitchShift.ar(sig, winSize, 2 ** (semitones / 12), 0, 0.004);
        env = EnvGen.kr(Env.asr(atk, 1, rel, \sin), gate, doneAction: 2);
        sig = sig * env * amp.dbamp;
        sig = LPF.ar(HPF.ar(sig, hpf), lpf);
        mid = (sig[0] + sig[1]) * 0.5;
        side = (sig[0] - sig[1]) * 0.5 * width;
        sig = [mid + side, mid - side];
        Out.ar(out, sig);
        Out.ar(revBus, sig * revSend);
    })
);
