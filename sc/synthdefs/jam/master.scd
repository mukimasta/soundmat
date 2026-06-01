// jam/master.scd — jamAudio.js masterFilter + masterTapeSat（web 无 limiter）
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\jam_master, { |melodyBus = 2, harmonyBus = 4, drumBus = 6,
        melodyGain = 0.48, harmonyGain = 0.4, drumGain = 0.48,
        cutoff = 14000, drive = 0, amp = 1, out = 0|

        var mel = In.ar(melodyBus, 2) * melodyGain;
        var harm = In.ar(harmonyBus, 2) * harmonyGain;
        var dr = In.ar(drumBus, 2) * drumGain;
        var sig = mel + harm + dr;
        var co = cutoff.clip(60, 18000);
        var lagged;

        lagged = Lag.kr(co, 0.2);
        sig = RLPF.ar(sig, lagged, 1.389);
        sig = RLPF.ar(sig, lagged, 1.389);

        sig = (sig * (drive < 0.0001)) + (~jamToneDistort.value(sig, drive) * (drive > 0.0001));

        Out.ar(out, sig * amp);
    })
);
