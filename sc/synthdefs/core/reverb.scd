// reverb.scd — 算法混响（ambient 用 aux 送；jam 不走全局混响）
//
// \reverb  读 REVERB_BUS → FreeVerb2 → 写 MIX_BUS。100% 湿声（干湿由各 voice revSend 控制）。
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\reverb, { |in = 8, out = 2, room = 0.85, damp = 0.3, amp = 0|
        var sig = In.ar(in, 2);
        sig = FreeVerb2.ar(sig[0], sig[1], 1.0, room, damp);
        Out.ar(out, sig * amp.dbamp);
    })
);
