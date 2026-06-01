// master.scd — 通用总线末级（ambient 用；jam 用 jam/master.scd 的 \jam_master）
//
// \master  读 MIX_BUS（sources 干声 + reverb 湿声汇总）→ 总音量 → 限幅 → 硬件输出
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\master, { |in = 2, out = 0, amp = 0, ceiling = -1|
        var sig = In.ar(in, 2);
        sig = sig * amp.dbamp;
        sig = Limiter.ar(sig, ceiling.dbamp, 0.01);
        Out.ar(out, sig);
    })
);
