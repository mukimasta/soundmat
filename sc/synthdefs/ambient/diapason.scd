// ambient/diapason.scd — 管风琴 drone 音色族（加性合成，从 sonification 迁移）
//
// \diapasonNote  单音 one-shot，linen 包络
// \diapasonHold  gated 持续 drone：asr 包络 + 缓慢音高漂移(±40cent) + 低通呼吸
// 12 谐波 -16dB/oct 自然滚降；干声 stereo（不走混响）。
(
var nHarmonics = 12, bp = 1, s1 = -16, s2 = -16, dl = 0;
var amps;
amps = (1..nHarmonics).collect { |n|
    var dB;
    if(n <= bp) { dB = s1 * n.log2 } { dB = (s1 * bp.log2) + (s2 * (n / bp).log2) };
    if(n.even) { dB = dB + dl };
    10.pow(dB / 20);
};

~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\diapasonNote, { |out = 0, freq = 65.41, amp = -9, atk = 0.3, sus = 4.0, rel = 0.5|
        var sig = Mix.fill(nHarmonics, { |i| SinOsc.ar(freq * (i + 1), 0, amps[i]) }) * 0.12;
        var env = EnvGen.kr(Env.linen(atk, sus, rel, 1, \sin), doneAction: 2);
        sig = sig * env * amp.dbamp;
        Out.ar(out, sig ! 2);
    })
);

~synthDefs = ~synthDefs.add(
    SynthDef(\diapasonHold, { |out = 0, freq = 65.41, amp = -9, gate = 1, atk = 4, rel = 5|
        var sig, env, pitchLfo, drift, lpfLfo;
        pitchLfo = SinOsc.kr(1/240).range(-40, 40);
        drift = 2 ** (pitchLfo / 1200);
        sig = Mix.fill(nHarmonics, { |i| SinOsc.ar(freq * drift * (i + 1), 0, amps[i]) }) * 0.12;
        lpfLfo = SinOsc.kr(1/160).range(600, 2500);
        sig = LPF.ar(sig, lpfLfo);
        env = EnvGen.kr(Env.asr(atk, 1, rel), gate, doneAction: 2);
        sig = sig * env * amp.dbamp;
        Out.ar(out, sig ! 2);
    })
);
)
