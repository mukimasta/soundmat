// compile.scd — 把 synthdefs/ 下所有 *.scd 的 SynthDef 编译成 compiled/*.scsyndef
//
// 各 .scd 把 SynthDef 追加进全局 ~synthDefs；这里递归扫描加载、统一 writeDefFile（离线
// 序列化，不需启动 scsynth）。加新音色 = 丢个 .scd 进 synthdefs/ 即可。
//
// 用法：sclang sc/compile.scd
(
var here = thisProcess.nowExecutingPath.dirname; // sc/
var defDir = here +/+ "synthdefs";
var outDir = here +/+ "compiled";

~synthDefs = [];

(outDir +/+ "*.scsyndef").pathMatch.do { |f| File.delete(f) };

// jam/00_common.scd 必须先于其它 jam synthdef（共享 ~jamToneFM 等 helper）
PathName(defDir +/+ "jam/00_common.scd").fullPath.load;
("  loaded  jam/00_common.scd").postln;

PathName(defDir).filesDo { |p|              // filesDo 递归子目录
    if(p.extension == "scd" and: { p.fileName != "00_common.scd" }) {
        p.fullPath.load;
        ("  loaded  " ++ p.fullPath.copyToEnd(defDir.size + 1)).postln;
    };
};

("compiling " ++ ~synthDefs.size ++ " synthdef(s) -> " ++ outDir).postln;
~synthDefs.do { |d|
    d.writeDefFile(outDir);
    ("  wrote   " ++ d.name ++ ".scsyndef").postln;
};

"done".postln;
0.exit;
)
