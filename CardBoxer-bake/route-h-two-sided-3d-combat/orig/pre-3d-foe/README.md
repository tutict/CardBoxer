# 牌拳 / CARD BOXER

卡牌驱动的 2D 横版格斗。角色不出招式指令，而是打出手牌：每张牌是一个动作，
牌序接上了就是连招，三张特定的牌加 3 点气就是大招。三局两胜，每回合 60 秒。

Godot 4.5（GL Compatibility）。**没有任何贴图资产**——角色、场景、界面全部由 GDScript 绘制。

![对局画面](docs/shots/arena.png)

## 跑起来

双击 `play-2d.bat`。它会去常见的几个位置找 Godot 4 编辑器并用本目录的 `project.godot` 启动。

或者手动：用 Godot 4 打开本目录的 `project.godot`。

纯逻辑校验（不开窗口，8 条断言）：

```
godot --headless --path . --script scripts/combo_check.gd
```

## 操作

| 键 | 作用 |
| --- | --- |
| `1` ~ `5` | 打出对应位置的手牌（出牌即出招，没有搓招） |
| `A` / `D` 或 `←` / `→` | 左右移动 |
| `R` | 重开一场 |
| `空格` | 暂停 |

## 玩法

- **手牌** 5 张，出掉的槽位约 2 秒后补一张。补牌保证手上至少有 2 张进攻牌。
- **气** 0–5 格。命中与被击各涨一点，随时间缓慢回复；第 4、5 格换了颜色，那是放大招的门槛。
- **连招** 1.9 秒内按序打出才接得上，取最长匹配，加伤并附带击飞/长硬直。
- **大招** 三张特定牌 + 3 点气：闪白、慢镜、超长硬直。
- **防守** 格挡减伤 80%（投技挡不住）；侧闪 0.18 秒无敌，闪过之后反击加伤 3。
- **反击** 交叉反击在对手出招途中打中，伤害翻倍。

完整卡牌表与连招表在 `docs/production-workflow.html`。

## 目录

```
project.godot          1280×720 / GL Compatibility / 主场景 scenes/main.tscn
scenes/main.tscn       一个 Node2D 挂 arena.gd，其余全部代码生成
scripts/card_data.gd   12 张牌与 10 条连招的唯一定义处
scripts/fighter.gd     状态机、命中判定、受击结算、关节姿态自绘
scripts/ai_controller.gd  读招 AI：先看距离，再看前摇/后摇，最后挑牌
scripts/arena.gd       回合流程、手牌经济、停帧与震屏、擂台绘制
scripts/hud.gd         血条、气槽、手牌、横幅（SystemFont 加载中文字体）
scripts/fx_layer.gd    特效专用层：必须盖在角色之上，否则伤害数字会被身体吃掉
scripts/combo_check.gd 连招确定性校验
docs/production-workflow.html      这份游戏是怎么被做出来的（含流水线实测记录）
docs/shots/            运行截图
```

## 和 Fantasy-Agent 的关系

这个游戏是用 `Fantasy-Agent` 这条流水线起头的：点子 → 玩法规格 → 导演计划 → Godot 工程。
流水线的策划段（spec / GDD / 计划 / QA / headless import）真的跑通了，
但它生成的可玩产物是固定的 3D 第三人称灰盒，表达不了 2D 卡牌格斗，而且它自己的 bot 试玩判了 `no_win_path`。

所以分工是：

- **流水线给的**：核心动词（position / attack / evade / recover，直接映射成四类牌）、
  四条失败压力（贪伤害有代价、位置是资源、前摇可读、读牌有回报）、GDD 与 QA 清单。
- **手写的**：卡牌表、连招表、状态机、命中判定、AI、全部画面与界面。

## 已知限制

- 没有音效与音乐。打击感目前只靠停帧、震屏、火花与伤害数字。
- 没有跳跃：位移全部由牌提供（突进 / 后撤 / 侧闪）。这是有意的取舍，不是缺失。
- 只有一名对手（青岚），难度固定。没有选人、没有剧情、没有存档。
- AI 会凑大招、会读前摇，但它不预判连段，也不会故意骗你出招。
