# Arrangements

编排是声音化的内容数据（`system_design/DATA_MODEL.md`「编排」）。每份编排是 `arrangements/` 下的一个文件夹，里面一个 `arrangement.toml`；文件夹名就是默认的编排标识。主机程序启动时读取全部编排，一份出错不影响其他编排，错误写进最近的警告。新的声音世界只需要新建一个文件夹；新的交互逻辑才需要写模式（`soundmat/sonification/<模式>/`，并在 `supervisor` 的 `MODES` 里登记）。

## 共同头部

```toml
title = "京都岚山"               # 控制台显示的名称（必需）
mode = "ambient"                 # 使用的模式（必需）
mode_label = "Ambient · 氛围"    # 控制台显示的模式说明
description = "……"               # 简短说明
ring_labels = ["低音", ...]      # 8 项：每环在控制台垫面页电平下方显示的名字
id = "kyoto"                     # 可省略，默认是文件夹名
```

头部之外的内容原样交给模式解释。模式在加载时检查结构、声明需要的素材和音色；不符合要求时加载失败，原因显示在控制台的编排列表里，当前编排不受影响。

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
