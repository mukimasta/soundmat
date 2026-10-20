# Arrangements

编排是声音化的内容数据（`system_design/DATA_MODEL.md`「编排」）。每份编排是 `arrangements/` 下的一个文件夹，里面一个 `arrangement.toml`；文件夹名就是默认的编排标识。主机程序启动时读取全部编排，一份出错不影响其他编排，错误写进最近的警告。新的声音世界只需要新建一个文件夹；新的交互逻辑才需要写模式（`soundmat/sonification/<模式>/`，并在 `supervisor` 的 `MODES` 里登记）。

## 共同头部

```toml
title = "京都岚山"               # 控制台显示的名称（必需）
mode = "ambient"                 # 使用的模式（必需）
mode_label = "Ambient · 氛围"    # 控制台显示的模式说明
description = "……"               # 简短说明
ring_labels = ["低音", ...]      # 8 项：每环的名字，默认的电平条用它
level = -12                      # 可省略：整体电平（dB，默认 0），见下文
[meters]                         # 可省略：控制台电平条怎样分组，见下文「电平条」
id = "kyoto"                     # 可省略，默认是文件夹名
```

`level` 是这份编排的整体电平：声音引擎把它乘在这份编排的混音总增益上（在模式总处理之后、总音量和限幅之前），用来对齐不同编排的响度，让总音量的同一个位置对每份编排都合适。调法是放满石头播放，看看板或垫面页的输出电平：密集处的峰值应在 −3 dBFS 左右，不要长时间贴着 −1 dB（那是总输出限幅器在压，会发喘、出毛刺）。Lo-Fi 设为 −12。

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

- 不声明 `placed` 时，每个发声的环一根：混音结构里有这一环的总线、并且这一环不是控制区；名字取 `ring_labels`。不声明 `background` 时这一组为空。京都岚山两组都不声明，Lo-Fi 和冥想只声明背景组。
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

## 声池编排

声池模式（`mode = "pool"`）是网页原型 Ambient（Sound Pool）的移植，各层的规则和数值都在代码里（`soundmat/sonification/pool/`，照抄网页），编排只决定哪一环放哪一层、多久换一次调：

```toml
[music]
key_dwell = [300, 480]          # 每个调停留多久（秒），之后沿五度圈换到下一个调

# 由内到外每环放哪一层，8 项，每层最多一环
rings = ["low_drone", "mid_drone", "pad", "mid_notes", "high_notes", "weather", "bells", "nature"]

[breath]                        # 底音的涌起落下和灯光共用的呼吸，可省略
period = 17.5                   # 一呼一吸多少秒（默认 17.5，网页底音 C 调时拍频的周期）
sound_depth_db = 30             # 底音最轻时比最响低多少 dB（0–60，默认 30）

[light]                         # 每项都可省略，用这里写的默认值
color = [255, 255, 255]         # 底色和石头标记的颜色，三个 0–255 的整数；三个相等时低亮度不偏色
breath_min = 0.0                # 呼吸最暗时的亮度（0–1）
breath_max = 0.10               # 呼吸最亮时的亮度（不小于 breath_min）
stone_alpha = 0.30              # 石头标记的亮度（0–1）
stone_width = 1                 # 石头标记两侧各点亮几颗（0–10）

[space]                         # 可省略，默认 [0.85, 1]
spread = [0.85, 1.0]            # 石头的声音定位时，圆心、外缘分别当作多大的半径

[[meters.background]]           # 底音不靠放石头、一直在响，作为背景电平条
label = "底音"
buses = ["bed"]
```

| 层 | 内容 |
|---|---|
| `low_drone` / `mid_drone` | 每颗石头一个持续的低音（第 2 / 第 3 八度，正弦加三角波 / 锯齿波），音高在五声音阶里随机取，同一个调里同一个位置不变 |
| `pad` | 每颗石头一个和声声部，每隔 4–8 秒起一个第 4 八度的正弦长音 |
| `mid_notes` / `high_notes` | 整环一个节奏的音符：中音符三角波、按石头数随机间隔；高音符正弦带回声、每 8 秒 |
| `bells` | 非谐波的钟声，每 6 秒 |
| `weather` | 风和雨：一颗只有风，每多一颗风减雨增，四颗起有雷 |
| `nature` | 鸟鸣和水滴，石头越多越密 |

此外一直有一层底音（总线 `bed`），空垫子时也响。音符、钟声的声音从这一环某颗石头的方位发出，低音与和声跟着各自的石头，底音、天气、自然不定位。空间化里半径越小声音越均匀地分到所有音箱，而冥想的层大多在内环，所以石头的半径先线性映射到 `space.spread`，默认让内环也几乎完全偏向所在一侧（立体声时用满左右）。

呼吸由模式计算（`pool/__init__.py` 的 `Breath`，0–1，从 0.5 开始先升）：底音每 0.25 秒收到一次这一段结束时的呼吸值，在合成器里线性滑过去，音量按 dB 随它线性变化（最响 0 dB、最轻 −`sound_depth_db`）；远处的音收到发声时的相位和频率，自己接着走、跟着 ±2 dB；灯光每拍取同一个值，底色亮度在 `breath_min`–`breath_max` 之间。所以改 `period` 时声音和灯光一起变。灯光由 `lights.py` 的 `warm_breathing` 画出，京都岚山的 `breathing_marks` 不受影响。混音结构里的总线是 `bed` 和 `ring0`…`ring7`，共用效果是 `sm_fx_pool`（网页的主混响）。

《冥想》就是网页原型的 Ambient，八层的顺序与网页由内到外一致；整体电平为 0：放满石头时响度约 −17 LUFS，与 Lo-Fi 相当。和网页的差别见 `system_design/SONIFICATION.md`「声池模式的运行」。

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
