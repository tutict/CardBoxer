# CardBoxer 3D建模与战斗动作精修实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 在不改变战斗规则和既有骨骼运行时契约的前提下，完成角色取景、模型蒙皮、动作辨识度和实机战斗表现的分阶段精修。

**方案：** 先锁定当前生产版的哈希与实机画面，再从相机取景开始排除裁切问题；之后只修复真实渲染能复现的模型与蒙皮缺陷，并精修动作关键姿势、过渡及战术变体。每一阶段都先生成独立检查证据，通过后再推广到正式 GLB 和动作库。

**技术栈：** Godot 4.5、GL Compatibility、Blender、GLB/glTF 2.0、Godot GDScript、现有动作 JSON 采样器。

**设计说明：** [2026-11-22 3D 建模与战斗动作精修设计说明](../specs/2026-11-22-3d-model-combat-polish.md)

## 全局约束

- 目标运行环境保持 Godot 4.5 与 GL Compatibility。
- 角色资源沿用 `CardBoxer/assets/3d/player-rigged.glb` 与 `foe-rigged.glb`。
- 动作数据沿用 `CardBoxer/data/combat_motion_3d.json` 的版本 1 契约、13 个运行时骨骼名、Godot Y-up/Z-forward 坐标和双方角色目录。
- 不改伤害、起手帧、收招规则、射程、碰撞结算、抽牌、随机种子或胜负逻辑。
- 先保留正式资源基线和哈希，试验成果放在 `CardBoxer-bake/3d-combat-polish/`，视觉验收通过后才推广。
- 不增加运行时依赖。导出的正式角色资源保持 GLB。

## 评审重点

- 实际窗口比例和最小尺寸下的脚、拳、扫腿与倒地裁切，在任务 1 和任务 2 检查。
- 镜头裁切与网格问题的归因混淆，在任务 1 和任务 2 检查。
- 肘、肩、髋、膝、头发和衣摆变形及穿插，在任务 3 检查。
- 分数动作帧、接触姿势和收招过渡出现脚滑或跳姿，在任务 4 检查。
- 玩家与对手朝向、尺寸、接触点、特效锚点或模式切换差异，在任务 5 检查。
- 战术变体共用动作后，视觉提示可能与动作名称不符，在任务 4 和任务 5 检查。

---

## 执行假设与工期

按一名技术美术兼 Godot 工程师、现有源资产可正常打开估算，总计约 7–10 个工作日。第一阶段先确认可编辑源文件与现有 GLB 的对应关系，再按实际问题调整模型阶段工作量。每一阶段的通过条件都保留独立判断权，可在达到质量要求后提前结束后续细化。

## Task 1：锁定基线并建立问题清单

**预计用时：** 0.5–1 个工作日。

**文件与输出：**
- 读取：`CardBoxer/assets/3d/player-rigged.glb`
- 读取：`CardBoxer/assets/3d/foe-rigged.glb`
- 读取：`CardBoxer/data/combat_motion_3d.json`
- 读取：`CardBoxer/scripts/fighter_3d_layer.gd`
- 读取：`CardBoxer/scripts/battle_presentation.gd`
- 读取：`CardBoxer/scripts/tactical_defs.gd`
- 新建：`CardBoxer-bake/3d-combat-polish/baseline/`

**步骤：**

- [ ] 记录玩家、对手 GLB 与动作 JSON 的 SHA-256、文件大小、Godot 版本、画布尺寸、窗口比例、启动模式和相机设置。
- [ ] 查明现有 GLB 对应的 Blender 源文件，核对导出时间、模型比例与骨架绑定。原始来源存在多个历史实验版本时，不把候选源文件覆盖成正式源文件。
- [ ] 使用生产渲染器捕获双方站姿、走动、刺拳、交叉拳、上勾拳、扫腿、投技、防御、闪避、受击和 KO 关键姿势。
- [ ] 为所有 19 个动作片段生成双方连续帧板，另存玩家与对手的反向朝向样本。
- [ ] 以可复现的正常战斗距离录制实际击中、格挡、闪避、招架、连续攻击和回合结束片段。
- [ ] 将每个发现标注为取景、轮廓、变形、动作节奏、接触或资源成本，并附关键帧截图和严重度。

**验收：**

- [ ] 基线记录能由第三方按相同窗口、模式和朝向复现。
- [ ] 所有问题均有当前生产 GLB 的实际 Compatibility 渲染作为证据。
- [ ] 区分相机裁切、角色原点或锚点偏移与网格本身的缺陷。

## Task 2：修正角色构图与画面可读性

**预计用时：** 0.5–1 个工作日。

**文件：**
- 可能修改：`CardBoxer/scripts/fighter_3d_layer.gd`
- 修改：`CardBoxer-bake/3d-combat-polish/framing/`
- 测试：`CardBoxer/tests/tactical_capture.gd`
- 测试：`CardBoxer/tests/native_live_check.gd`

**步骤：**

- [ ] 使用任务 1 的标记重现刺拳、格挡、扫腿和倒地裁切问题。
- [ ] 先调相机距离、正交缩放、角色 viewport 边距或投影视图定位；保留能表现拳脚延伸和低姿势的完整取景范围。
- [ ] 校验 16:9 主尺寸与支持的最小窗口尺寸。全部人体轮廓和有效接触端点至少保留画面短边 4% 的安全边距。
- [ ] 比较玩家和对手同一姿势下的屏幕高度、脚底线、头部空间、接触距离和视觉中心。
- [ ] 再次捕获任务 1 的取景样本，记录前后对照和相机参数。

**验收：**

- [ ] 代表性攻击、低扫和倒地姿势均保持全身与有效端点可见。
- [ ] 玩家和对手的脚底线稳定，接触动作仍与战斗逻辑对齐。
- [ ] 取景变化不会遮挡牌面界面或压缩有效战斗区域。

## Task 3：局部模型与蒙皮修复

**预计用时：** 2–3 个工作日。

**文件：**
- 试验源文件：`CardBoxer-bake/3d-combat-polish/authoring/`
- 试验导出：`CardBoxer-bake/3d-combat-polish/candidates/`
- 候选正式资源：`CardBoxer/assets/3d/player-rigged.glb`
- 候选正式资源：`CardBoxer/assets/3d/foe-rigged.glb`
- 测试：`CardBoxer/tests/native_motion_check.gd`
- 测试：`CardBoxer/tests/native_rig_check.gd`

**步骤：**

- [ ] 逐项复现任务 1 的肩肘连接、髋膝变形、角色穿插、玩家头发或衣摆拉伸问题。
- [ ] 按问题优先级修局部拓扑、曲面体积或现有骨骼权重。先使用已存在的源模型，保持角色整体轮廓和身份设计连续。
- [ ] 如果仅少量异常顶点造成尖刺，限定修补范围，冻结非目标顶点权重，检查重复位置、法线分界和接缝连续性。
- [ ] 导出 GLB 前检查模型尺度、朝向、根节点与 pivot、命名、材质复用、纹理尺寸及休息姿势。
- [ ] 使用 Godot `--headless --editor --import` 导入候选资源，并生成相同动作与朝向的真实渲染样本。
- [ ] 仅在测得资源负担影响启动或运行后，才做纹理或几何优化。优化前后比较画面、资源大小和运行时启动结果。

**验收：**

- [ ] Godot 导入后的骨骼名称、顺序、父级、rest、bind、角色比例和朝向满足现有运行时检查。
- [ ] 所有 19 个片段的角色变形均复查，不出现可见尖刺、网格裂缝、肢体分离或明显穿插。
- [ ] 非目标 GLB 数据保持原样，权重修补范围和变化顶点可从对比报告追溯。
- [ ] 资产大小变化有记录。通过画面验收前保留原始 GLB 和可回退候选。

## Task 4：动作姿势、节奏与战术语义精修

**预计用时：** 2–3 个工作日。

**文件：**
- 修改：`CardBoxer/data/combat_motion_3d.json`
- 可能修改：`CardBoxer/scripts/battle_presentation.gd`
- 可能修改：`CardBoxer/scripts/tactical_defs.gd`
- 修改：`CardBoxer-bake/3d-combat-polish/motion-review/`
- 测试：`CardBoxer/tests/native_motion_check.gd`
- 测试：`CardBoxer/tests/battle_rhythm_check.gd`
- 测试：`CardBoxer/tests/battle_contact_spacing_check.gd`

**步骤：**

- [ ] 首先精修高可见度动作：刺拳、交叉拳、上勾拳、扫腿、投技、格挡、招架和受击反应。
- [ ] 调整每个重点动作的预备、加速、接触、收势姿势，使发力方向和受力方向在真实战斗距离下一眼可辨。
- [ ] 检查站姿、待机呼吸、走动、后撤、突进、气功波、蓄势、卸力、轻重受击、格挡和 KO 的动作完整性与过渡。
- [ ] 逐一审阅两名角色的 19 个片段，按角色体型调整独立姿态。双方保留相同动作语义，避免简单镜像导致角色身份混淆。
- [ ] 为佯攻、招架、延迟重拳、破防击、霸体重拳和追击拳分别设计易读的预备姿态、停顿或跟进动作。只有动作映射确实无法区分时才增加专用动作片段。
- [ ] 保留既有分段长度、接触帧与逻辑时钟。动画变化不触发二次伤害、不改变随机结果或角色逻辑位置。
- [ ] 用关键帧表、连续 GIF 和实机交换录像审查动作节奏、脚滑、关节边界和屏幕轮廓。

**验收：**

- [ ] `native_motion_check.gd` 对两名角色的 19 个片段、按当前测试覆盖的采样点全部通过，支撑脚误差低于 0.020 米且不高于任务 1 记录的当前基线。
- [ ] 每个攻击命中帧与运行时接触帧匹配，支撑脚和发力脚符合动作意图。
- [ ] 六种战术动作在同等镜头尺寸下可按姿态识别，所有战斗规则数值不变。
- [ ] 两个朝向播放连续自然，阶段交界无明显跳变，局部受击和 KO 能正确结束及复位。

## Task 5：游戏整合、跨模式回归与交付

**预计用时：** 1–2 个工作日。

**文件：**
- 资源：`CardBoxer/assets/3d/`
- 数据：`CardBoxer/data/combat_motion_3d.json`
- 报告：`CardBoxer-bake/3d-combat-polish/release-review/`
- 验证：`CardBoxer/tests/native_startup_check.gd`
- 验证：`CardBoxer/tests/native_live_check.gd`
- 验证：`CardBoxer/tests/battle_contact_spacing_check.gd`
- 验证：`CardBoxer/tests/tactical_integration_check.gd`
- 验证：`CardBoxer/tools/verify_tactical.py`

**步骤：**

- [ ] 将通过单资产检查的 GLB 与动作 JSON 推广到游戏，并记录最终 SHA-256。
- [ ] 重新导入资源后运行动作采样、骨架、启动和接触点检查。
- [ ] 在战术、太鼓和实时模式下录制同一组攻击、防御、闪避、受击、KO、复位与连续战斗用例。
- [ ] 使用实际发布渲染路径复核相机安全边距、角色材质、接触特效锚点、双方朝向和 HUD 遮挡。
- [ ] 运行 `tools/verify_tactical.py` 与现有 launcher 验证，确保启动入口、模式切换和发布资源均正常。
- [ ] 保存最终截图、动作检查摘要、文件哈希、尺寸对比和问题关闭记录，未关闭项注明影响范围及后续决策。

**验收：**

- [ ] 项目现有动作、骨架、接触点、战术和启动回归全部通过。
- [ ] 三种战斗模式的玩家与对手均加载正式 3D 资源，无脚本错误或资源缺失。
- [ ] 发布包仍可正常启动。更新前后的资源哈希与包体变化有完整记录。
- [ ] 只把实机画面和跨模式检查均通过的资源标记为最终版本。

## 交付清单

- 两份通过导入与变形验收的角色 GLB。
- 通过实机验收的双方动作 JSON。
- 每阶段基线与前后对照截图、连续动作板和源哈希记录。
- 动作采样、骨架、接触点、战术与发布启动验证摘要。
- 仍待处理问题及其复现步骤。

