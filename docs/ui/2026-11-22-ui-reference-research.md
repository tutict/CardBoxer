# CardBoxer 界面参考调研

调研日期：2026-11-22（北京时间）。通过浏览器实际打开来源页面并查看截图；以下设计判断是针对 CardBoxer 的提炼，不是参考游戏的官方设计结论。

## 已核实的参考

| 编号 | 来源与证据 | 可借鉴的做法 | 在 CardBoxer 中的应用 |
|---|---|---|---|
| R1 | [Fights in Tight Spaces：官方 Steam 页面](https://store.steampowered.com/app/1265820/Fights_in_Tight_Spaces/)；查看完整游戏截图与页面媒体 | 战场、底部手牌和情境说明有不同职责；聚焦一张牌时再显示完整解释 | 保持擂台与大手牌，主界面只承担读牌、编排和简短结果；完整时序参数放在详情 |
| R2 | [Slay the Spire：Enemy stats 截图档案](https://interfaceingame.com/screenshots/slay-the-spire-enemy-stats/) | 敌方意图以符号和数值直接呈现，悬停说明补充条件；截图可见攻击、策略与未知意图 | 为公开招式突出动作类别与射程；暗牌统一保留问号；给玩家预估增加明确的不确定性标识 |
| R3 | [Balatro：官方 Steam 页面](https://store.steampowered.com/app/2379780/Balatro/)；查看 Two Pair、40×2 和顶部小丑的完整截图 | 常驻被动、牌型结果、当前打出的牌、手牌分别占据稳定位置 | 天赋条保持固定；牌型加成放在编排行标题边缘；触发时只强调对应天赋 |
| R4 | [Street Fighter V：Round 1 截图档案](https://interfaceingame.com/screenshots/street-fighter-v-round-1/) | 血条、角色名和资源沿画面边缘组织；开局大字属于短暂演出 | 保留双方血条、中央局数和比分，减弱常驻管理按钮；增加擂台可见区域 |
| R5 | [Xbox Accessibility Guideline 101：Text display](https://learn.microsoft.com/en-us/gaming/accessibility/xbox-accessibility-guidelines/101) | PC/VR 在 1080p 下默认字形主体高度至少 18px；字号要从截图中的实际字形测量，不能只看代码中的字号 | 提升计划数值、射程与原因文字的字号；用真实 GPU 截图确认实际可读性 |
| R6 | [Xbox Accessibility Guideline 102：Contrast](https://learn.microsoft.com/en-us/gaming/accessibility/xbox-accessibility-guidelines/102) | 常规重要文字和视觉信息对比度至少 4.5:1；大元素与禁用文字至少 3:1；非纯色背景要检查最低对比区域 | 保留深色稳定底板；分别检查正常、禁用、悬停、选中和战斗背景上的文字 |
| R7 | [Xbox Accessibility Guideline 103：Additional channels for visual and audio cues](https://learn.microsoft.com/en-us/gaming/accessibility/xbox-accessibility-guidelines/103) | 颜色不能独自表达重要信息；文字、形状与符号应能补充颜色 | 射程使用带文字的三格标记；确定和不确定预估使用不同边框及词语；命中与失败都有文字 |

R2、R4 是游戏截图档案，适合研究布局，不代表游戏当前版本。R5–R7 是验收依据的参考；采用其中若干规则不等于完成整套 XAG 无障碍认证。

### 实际查看的图片

- [R1：完整战场、聚焦卡牌与手牌](https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1265820/ss_0ea5ac7cbe02ce5bef48ee1cd61a99f3cbeff6d3.1920x1080.jpg?t=1774909410)。另一张官方截图的敌人头顶数值辅助了意图呈现的比较。
- [R3：常驻小丑、牌型与手牌分区](https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/2379780/96208723dbedef49d71bf1b0a74aee1689018c50/ss_96208723dbedef49d71bf1b0a74aee1689018c50.1920x1080.jpg?t=1790693638)。另查看了 Justice 卡牌说明截图。
- [R4：沿边缘组织的格斗 HUD](https://interfaceingame.com/wp-content/uploads/street-fighter-v/street-fighter-v-round-1.png)。

## 当前工程的证据

当前实现是 Godot 4.5 的手绘 Control HUD，不是网页。依据包括：

- [tactical_hud.gd](../../CardBoxer/scripts/tactical_hud.gd)、[tactical_forecast.gd](../../CardBoxer/scripts/tactical_forecast.gd)、[tactical_match.gd](../../CardBoxer/scripts/tactical_match.gd)。
- [已批准的五拍规则与界面约束](../superpowers/specs/2026-11-22-five-beat-design.md)。
- [此前试玩后的 HUD 精简要求](../../CardBoxer-bake/gameplay-integration/spec.md)：大手牌、54px 紧凑计划槽、低饱和、少文字、悬停详情。
- [编排完成](../../logs/ui-reference-plan-shots/06-ordered-plan.png)、[十张手牌](../../logs/ui-reference-plan-shots/05-ten-hand.png)、[预估详情](../../logs/ui-reference-plan-shots/06c-recovery-and-forecast.png)、[射程打空原因](../../logs/ui-reference-plan-shots/11-range-miss-reason.png)、[天赋选择](../../logs/ui-reference-plan-shots/01-loadout.png)。

上述 GPU 截图生成于 2026-11-22 16:18，晚于 HUD 源文件的 14:54 修改时间；捕获日志记录 native=true、双方 3D 骨骼加载和新增反馈场景完成。此证据能证明渲染状态，不能代替真人操作验证。

### 主要观察

1. 五拍已经按列对齐、当前拍也会同时强调双方；下一步应增强编排时的同拍关联，而不是重复建设已有功能。
2. 计划槽把起手、伤害、射程、预估或结果拼在一行 12px 文字里；手牌射程为 13px，主次关系不够清楚。
3. `forecast_certain` 已由视图模型提供，绘制尚未用它区分样式。该字段只代表结果类别一致，不能推出伤害值唯一或敌方暗牌已知。
4. 暂停、重开、换牌按钮都有金色描边，与开打及选中反馈竞争。降低次要控件的强调程度即可改善，不需要替换整个配色体系。
5. 射程打空、起手被打断、防御过早等原因已经实现；但任意悬停会隐藏整组来源面板，进入下一轮后只留下会省略的单行摘要。
6. 天赋六选三页面的完整文字本来较清楚，优先级低于战斗编排；适合统一风格和强调触发顺序，避免为装饰增加额外阅读。

按源代码 RGB 值计算，常规手牌深底上的分类色文字对比度约为：攻击 6.23:1、防御 7.90:1、位移 8.82:1、调整 7.54:1，次要文字 12.66:1。这只是静态配色计算；不能替代合成背景、抗锯齿和禁用状态的截图检查。主要问题是字号、层级和信息呈现，而不是常规牌面必然低于对比度要求。

## 调研结论

推荐保留现有世界观与深色 HUD，以“格斗 HUD 的稳定边缘信息 + 同拍对位的编排区 + 大手牌”为结构。借鉴参考的功能组织，不复刻像素字、重度装饰、网格战场或扑克牌桌。

未采用的来源：[Game UI Database](https://gameuidatabase.com/) 在本次访问返回 `Database Unavailable`，未将搜索摘要当作截图证据。

实施方案见 [界面优化方案](../superpowers/plans/2026-11-22-ui-optimization-plan.md)。[布局示意图](2026-11-22-ui-layout.png) 的可重复生成脚本为 [render_ui_layout.py](render_ui_layout.py)，使用当前擂台截图片段与目录中的卡牌数据做规划样例，不是实施后的运行截图。
