// jam/master.scd — jamAudio.js masterFilter + masterTapeSat（web 无 limiter）
// cutoff/drive 由 Python MasterFX 平滑后写入；此处 100% 低通 + 饱和干湿比，无 SC Lag / 干声混入。
~synthDefs = ~synthDefs ? [];

~synthDefs = ~synthDefs.add(
    SynthDef(\jam_master, { |melodyBus = 2, harmonyBus = 4, drumBus = 6,
        melodyGain = 0.48, harmonyGain = 0.4, drumGain = 0.48,
        cutoff = 14000, drive = 0, lofiGain = 1, amp = 1, out = 0|

        var mel = In.ar(melodyBus, 2) * melodyGain;
        var harm = In.ar(harmonyBus, 2) * harmonyGain;
        var dr = In.ar(drumBus, 2) * drumGain;
        var sig = mel + harm + dr;
        var co = cutoff.clip(60, 18000);
        var satWet;

        sig = RLPF.ar(RLPF.ar(sig, co, 1.389), co, 1.389);

        satWet = (drive / 0.025).clip(0, 1);
        sig = ~jamDistWet.value(sig, drive, satWet);

        Out.ar(out, sig * amp * lofiGain);
    })
);
