// jam/reverb_bus.scd — 共享 reverb（设计文档：每路 marimba 自带 reverb 改成 send/return）
//
// 路径：voice → JAM_REVERB_BUS（×revSend）→ 单实例 reverb（100% wet）→ MELODY_BUS
// 节点顺序：voices (HEAD) → harmony_group → jam_reverb_bus → jam_master (TAIL)
// 同一 reverb tail 服务所有马林巴；CPU 从 N×reverb 降到 1×reverb，听感与 inline reverb 几乎一致。
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\jam_reverb_bus, { |in = 10, out = 2, decay = 1.4, preDelay = 0.02, amp = 1|
        var sig = In.ar(in, 2);
        var dryWet = ~jamToneReverb2.value(sig[0], sig[1], 1.0, decay, preDelay);
        Out.ar(out, [dryWet[0], dryWet[1]] * amp);
    })
);
