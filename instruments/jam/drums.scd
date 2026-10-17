// Jam 鼓（移植自第一版 sc/synthdefs/jam/drums/）。参数 amp（力度，ghost 为 0.38）。
~smDef.("jam_kick", {
    var fenv = EnvGen.kr(Env.perc(0.001, 0.06, 1, -8));
    var env = EnvGen.kr(Env.perc(0.001, 0.22, 1, -4), doneAction: 2);
    ~smOut.(SinOsc.ar(48 * (1 + (fenv * 6))) * env * \amp.kr(1));
});

~smDef.("jam_snare", {
    var env = EnvGen.kr(Env.perc(0.001, 0.12, 1, -4), doneAction: 2);
    ~smOut.(WhiteNoise.ar * env * \amp.kr(1) * 0.75);
});

~smDef.("jam_hihat", {
    var env = EnvGen.kr(Env([0, 1, 0, 0], [0.001, 0.028, 0.006], [\lin, -4, -4]), doneAction: 2);
    ~smOut.(HPF.ar(HPF.ar(WhiteNoise.ar * env * \amp.kr(1), 4800), 4800));
});
