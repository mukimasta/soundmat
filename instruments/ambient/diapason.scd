// 管风琴 drone（加性合成，移植自第一版 sc/synthdefs/ambient/diapason.scd）。
// 12 个谐波 -16 dB/oct 自然滚降，缓慢音高漂移（±40 音分）与低通呼吸。持续声部，靠 gate 淡出。
(
var nHarmonics = 12;
var amps = (1..nHarmonics).collect { |n| 10.pow((-16 * n.log2) / 20) };
~smDef.("diapasonHold", {
    var freq = \freq.kr(65.41);
    var drift = 2 ** (SinOsc.kr(1/240).range(-40, 40) / 1200);
    var sig = Mix.fill(nHarmonics, { |i| SinOsc.ar(freq * drift * (i + 1), 0, amps[i]) }) * 0.12;
    sig = LPF.ar(sig, SinOsc.kr(1/160).range(600, 2500));
    sig = sig * ~smGateEnv.value * \amp.kr(-9).dbamp;
    ~smOut.(sig);
});
)
