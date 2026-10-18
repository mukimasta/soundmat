// 编译全部音色：sclang instruments/build.scd
//
// 每个音色按声道数 2、4、8 各编译一份，名字后缀声道数（例如 marimbaNote_2）。主机程序按当前
// 音箱布局的声道数选用；声道数在 SynthDef 编译时固定，所以要分别编译。
// 产物写到 instruments/compiled/（不进仓库，部署时随程序同步到树莓派）。
(
var here = thisProcess.nowExecutingPath.dirname;
var outDir = here +/+ "compiled";
var files = [];
File.mkdir(outDir);
(outDir +/+ "*.scsyndef").pathMatch.do { |f| File.delete(f) };
["players", "ambient", "jam", "pool", "system"].do { |dir|
    files = files ++ (here +/+ dir +/+ "*.scd").pathMatch.sort;
};
[2, 4, 8].do { |n|
    ~numCh = n;
    ~synthDefs = [];
    (here +/+ "lib/common.scd").load;
    (here +/+ "lib/jam_common.scd").load;
    (here +/+ "lib/tone.scd").load;
    (here +/+ "lib/pool_common.scd").load;
    files.do { |f| f.load };
    ~synthDefs.do { |d| d.writeDefFile(outDir) };
    ("% 声道：% 个音色".format(n, ~synthDefs.size)).postln;
};
"完成：%".format(outDir).postln;
0.exit;
)
