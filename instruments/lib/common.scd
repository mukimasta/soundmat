// 所有音色共用的约定（docs/implementation/SYNTH.md）。
//
// ~numCh：当前编译的声道数（等于音箱数）。音色把信号交给 ~smOut，由它按主机程序给出的增益
// 分配到各只音箱，写到声部所在的环总线（out），以及共用效果的发送总线（fx）。
//   单声道信号：增益 g0..g{N-1}
//   立体声信号：左声道增益 gl0..，右声道增益 gr0..
// 增益带 50 ms 平滑，位置变化不会产生咔嗒声。

~smDef = { |name, func|
    ~synthDefs = ~synthDefs.add(SynthDef((name ++ "_" ++ ~numCh).asSymbol, func));
};

~smGains = { |prefix|
    ~numCh.collect { |i| NamedControl.kr((prefix ++ i).asSymbol, 1 / ~numCh.sqrt, 0.05) }
};

~smSpatial = { |sig|
    if(sig.size == 2) {
        var gl = ~smGains.("gl"), gr = ~smGains.("gr");
        ~numCh.collect { |i| (sig[0] * gl[i]) + (sig[1] * gr[i]) }
    } {
        var g = ~smGains.("g");
        ~numCh.collect { |i| sig * g[i] }
    }
};

// dry 写到环总线；wet（可选）写到共用效果的发送总线
~smOut = { |dry, wet|
    Out.ar(\out.kr(0), ~smSpatial.(dry));
    if(wet.notNil) { Out.ar(\fx.kr(0), ~smSpatial.(wet)) };
};

// 持续声部的淡入淡出：gate 置 0 时按 rel 淡出并释放
~smGateEnv = {
    EnvGen.kr(Env.asr(\atk.kr(0.05), 1, \rel.kr(0.5), \sin), \gate.kr(1), doneAction: 2)
};
