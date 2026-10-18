# Arrangements

编排是声音化的内容数据（`system_design/DATA_MODEL.md`「编排」）。每份编排是 `arrangements/` 下的一个文件夹，里面一个 `arrangement.toml`；文件夹名就是默认的编排标识。主机程序启动时读取全部编排，一份出错不影响其他编排，错误写进最近的警告。新的声音世界只需要新建一个文件夹；新的交互逻辑才需要写模式（`soundmat/sonification/<模式>/`，并在 `supervisor` 的 `MODES` 里登记）。

## 共同头部

```toml
title = "京都岚山"               # 控制台显示的名称（必需）
mode = "ambient"                 # 使用的模式（必需）
mode_label = "Ambient · 氛围"    # 控制台显示的模式说明
description = "……"               # 简短说明
ring_labels = ["低音", ...]      # 8 项：每环的名字，默认的电平条用它
[meters]                         # 可省略：控制台电平条怎样分组，见下文「电平条」
id = "kyoto"                     # 可省略，默认是文件夹名
```

头部之外的内容原样交给模式解释。模式在加载时检查结构、声明需要的素材和音色；不符合要求时加载失败，原因显示在控制台的编排列表里，当前编排不受影响。

## 电平条

控制台垫面页下方的电平条，每一层声音一根，分成两组：`background`（不靠放石头、自己在走的部分，例如 Jam 的和声和鼓）和 `placed`（由放置的石头触发的部分）。编排可以声明：

```toml
[[meters.background]]
label = "和声"                   # 条下面显示的名字
buses = ["harmony"]              # 这一层的总线；可以列多条，电平取最大值

[[meters.background]]
label = "鼓"
buses = ["drums"]
color = "#8A847A"                # 可省略：指示色；只对应一个环时默认用这一环的颜色

[[meters.placed]]                # 可省略，见下面的默认规则
label = "外圈"
buses = ["ring7"]
```

- 不声明 `placed` 时，每个发声的环一根：混音结构里有这一环的总线、并且这一环不是控制区；名字取 `ring_labels`。不声明 `background` 时这一组为空。京都岚山两组都不声明，Lo-Fi 只声明背景组。
- 引用的总线必须在模式声明的混音结构里，否则编排加载失败。所以把鼓拆成几条总线（例如 kick、snare、hihat）后，这里列出这几条，控制台上仍然是一根"鼓"；增加新的背景元素也只需要改编排文件。
- 实现在 `soundmat/sonification/meters.py`。

## 声音素材的引用

编排只引用素材，不包含素材：引用是声音素材库 `samples/` 下的相对路径，例如 `kyoto/ring3/wind/…wav`。素材库的位置是设置 `run.soundLibrary`，默认依次查找程序目录旁的 `sound/`（树莓派上的 `/home/soundmat/sound`）和 SoundMat 总文件夹的 `sound/`（开发机），也可以用环境变量 `SOUNDMAT_SOUND` 指定。缺失的素材不阻止编排加载：控制台在编排上提示缺少几个，加载时写进最近的警告，用到它们的声音不发声。素材按 32 位浮点估算内存（帧数 × 声道数 × 4 字节），超过配置 `sound.asset_memory_mb` 时整份编排拒绝加载。

## Ambient 编排

```toml
[music]
root = 60                  # 音阶的起点（MIDI 音高）
scale = [0, 2, 4, 7, 9]    # 音阶各级相对起点的半音数

[defaults]                 # 素材角色的默认参数（合成音色不套用）
amp = -12

[samples.wind_small]       # 素材表：名字 → 文件和该素材的默认参数
file = "kyoto/ring3/wind/335891__….wav"
amp = -14

[rings.3.wind]             # 第 3 环的角色 wind
behavior = "sustained"     # sustained / intermittent / trigger
tiers = [                  # 按这一环的石头数分档（取不超过当前数量的最高档）
    { count = 1, sample = "wind_small", amp = -15 },
    { count = 2, sample = "wind_big", amp = -11 },
]
```

角色的键：

| 键 | 含义 |
|---|---|
| `behavior` | `sustained` 有石头就持续响；`intermittent` 有石头时以随机间隔触发；`trigger` 放下石头时响一次 |
| `instrument` | 使用的音色（SynthDef 名），与 `samples` / `tiers` 二选一 |
| `samples` | 素材名列表：持续角色用第一个，触发与间歇角色每次随机选一个 |
| `tiers` | 按石头数分档的素材，档位改变时旧档淡出、新档淡入 |
| `interval` | 间歇角色的间隔范围 `[最短, 最长]`（秒），每次在范围内随机 |
| `position` | `none` 不定位（持续的默认）、`zone` 放下石头的区域中心（触发的默认）、`centroid` 这一环所有石头的方位重心、`random` 随机方位（间歇的默认） |
| `when_rings` / `unless_rings` | 条件：列出的环都有石头 / 都没有石头时角色才生效 |
| `priority` | 声部超出预算时的优先级；默认持续 2、触发 1、间歇 0 |
| 其他键 | 作为数值参数交给音色，例如 `amp`（dB）、`decay`、`freq`、`semitones`、`winSize`、`revSend` |

持续角色的 `atk`、`rel` 用作声部的淡入、淡出时长（秒），不再作为参数传给音色。音色角色在触发时如果没有给出 `freq`，按区域取音高：环内序号按两半对称映射到音阶（与第一版相同）；间歇触发在两个八度的音阶里随机取音。

《京都岚山》由第一版 `manifest/ambient/kyoto.toml` 转换而来，声音内容不变；位置策略取默认值，与第一版的声像一致（持续声居中，触发按扇区，间歇随机）。

## Jam 编排

```toml
[music]
bpm = 120
key = "C"                       # 调；改调即全局移调
scale = "major"                 # major / natural_minor / harmonic_minor / dorian
scheme = 2                      # 时间方案 1 / 2 / 3（见 soundmat/sonification/jam/timing.py）
lookahead = 0.1                 # 前瞻时间窗（秒）

[control]                       # 控制区；压力数值是 ADC 原始读数之和（满量程 4095）
rings = [0, 1]
start_threshold = 250           # 超过即开始播放
release_hold = 0.1              # 压力消失超过这么久才算松开（秒）
lofi_range = [1000, 8000]       # 压力和在此区间内映射为 Lo-Fi 0–1000
preview_idle = 0.5              # 空闲时放下石头的预听力度（0 = 不预听）
preview_playing = 0.0           # 播放中放下石头的预听力度

[lofi]                          # Lo-Fi 强度 → 模式总处理参数，分段线性 [[强度, 值], ...]
cutoff = [[0, 14000], [1000, 2425]]
drive = [[0, 0.0], [1000, 0.025]]
gain = [[0, 1.0], [1000, 1.45]]

[mix]                           # 各总线的增益：ring2…ring7、harmony、drums
harmony = 0.4

[instruments]                   # 和声与鼓用的音色
pad = "jam_chord_pad"

[[progression]]                 # 和弦进行：小节数与 5 音配音（首调级数）
id = "2m9"
bars = 2
voicing = ["2_", "4_", "6_", "1", "3"]

[rings.7]                       # 触发环
role = "melody"                 # melody 用 note_sec；bass 的时长 = 四分音符 + tail_sec
instrument = "jam_marimba"
note_sec = 2.012
gain = 2.75                     # 该环增益（作为 ringGain 参数交给音色）
# 其他键作为数值参数交给音色，例如 far = 1

[triggers."2m9"]                # 触发表：和弦 → 环 → 8 个八分位的音级（"null" 不发声）
7 = ["3^", "1^", "2^", "3^", "3^", "2^", "1^", "6"]

[drums]                         # 十六分位 0 休止 / 1 正常 / 2 ghost
sequence = ["A", "B", "C"]      # 曲式：每项是一个和声循环（方案 2 为 8 小节）
[drums.patterns.A]
kick = [0, 0, ...]              # 16 个
```

音级记号：1–7 是当前调音阶的音级，升降写在数字后（`#` / `b`），八度写在最后（`^` / `_`，可叠加），无八度记号为第 4 八度，例如 `1#^`。

Jam 发出的参数：和声声部 `freq0`…`freq4`、`amp`；鼓 `amp`（ghost 为 0.38）、`sustain`；旋律与贝斯 `freq`、`velocity`（同一扇区组 N 颗石头时为 1/√N，下限 0.2）、`ringGain`、`sustain` 和该环的额外参数。全局参数：`cutoff`、`drive`、`lofiGain`，以及 `bus.<总线>` 形式的各总线增益。

《Lo-Fi Loop · Progression 1》由第一版 `manifest/jam/lofi_1.toml` 及其引用的 YAML 合并转换而来，音乐内容不变。

### 精确时刻的计算

扫描线位置以扇区为单位，是音乐时间的线性函数（方案 2、120 BPM 时每秒 8 个扇区）。每一拍把前瞻时间窗换算成音乐时间区间 `[已排到, 当前 + 提前量)`，直接解出扫描线经过各有石头的触发扇区中心的时刻，以及区间内的十六分格时刻，生成定时事件；区间是半开的，相邻两拍不会重复也不会遗漏。第一版按帧比较扫描角前后两次的位置，命中时刻会落在帧上；新版的命中时刻精确到扫描线经过的那一刻。
