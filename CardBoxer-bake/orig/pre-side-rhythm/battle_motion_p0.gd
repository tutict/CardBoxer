extends RefCounted
## 回合制合战 P0 动作接线层 —— 纯常量 + 纯函数，无节点、无状态。
##
## 真相来源：CardBoxer-bake/combat-motion-design/battle_motion_spec.json
## 的 card_type_binding / damage_tiers。这里只落 **asset_plan.reuse**：
## focus（亮牌仪式）、jab / cross / wave（赢家攻击）、hit_light / hit_heavy
## （fighter.gd 按 extra 自动选的受击轨道）。
##
## spec 里标 new: 的 10 项（reveal_ready / reveal_present / reveal_hold /
## ex_charge / ex_burst / hit_crush / round_victory / round_defeat /
## round_settle / ko_fall）一律**尚未烘**，本文件不假装已有资产。
## 所以：
##   * reveal 阶段统一播 focus，不播任何招式（P1 亮牌不打架）；
##   * triple 的 loser_react 字段只是规格索引，实际受击轨道由
##     extra="super" 触发 fighter.gd 的 0.75s 硬直 + reuse:hit_heavy；
##   * EX 仍只有牌型升级与 HUD 标记，没有专属蓄力/爆发动作。
##
## 伤害公式不在这里：Rules.damage_of() 已经给出三同 15..23 /
## 三连 12..18 / 散牌 6..13，接线只负责把「动作 id / 受击档」交给
## arena，不改数值，避免破坏既有玩法平衡。

const SPEC_VERSION := "1.0-p0"

## 亮牌仪式：reuse:card:focus。perform_visual() 会顺带把角色置为
## _visual_only，亮牌阶段因此不可能漏进实时命中判定。
const REVEAL_CARD := "focus"

## 牌型 → 赢家动作 / 输家受击档 / HUD 中文名 / 资产索引。
## extra 直接传给 fighter.gd 的 apply_hit()，对应已有的
## 0.26 / 0.42 / 0.5 / 0.75 秒四档硬直，不需要改 fighter.gd。
const BINDINGS := {
	"triple": {
		"winner_card": "wave", "react": "hit_crush", "extra": "super",
		"label": "气功波", "asset": "reuse:card:wave",
	},
	"sequence": {
		"winner_card": "cross", "react": "hit_heavy", "extra": "launch",
		"label": "交叉反击", "asset": "reuse:card:cross",
	},
	"scatter": {
		"winner_card": "jab", "react": "hit_light", "extra": "",
		"label": "刺拳", "asset": "reuse:card:jab",
	},
}

## 平局：双方各受 3 点，不播赢家攻击（P3）。
const DRAW := {"react": "hit_light", "extra": "", "label": "对峙"}


static func binding_for(type: String) -> Dictionary:
	var b: Dictionary = BINDINGS.get(type, BINDINGS["scatter"])
	return b


static func winner_card(type: String) -> String:
	return String(binding_for(type).get("winner_card", "jab"))


static func hit_extra(type: String) -> String:
	return String(binding_for(type).get("extra", ""))


static func react_name(type: String) -> String:
	return String(binding_for(type).get("react", "hit_light"))


static func label_of(type: String) -> String:
	if type == "":
		return String(DRAW["label"])
	return String(binding_for(type).get("label", ""))


## 给自检用：所有引用到的 reuse 资产名，逐项可对照 card_motion.json。
static func reuse_assets() -> Array:
	return [
		"focus", "jab", "cross", "wave",
		"hit_light", "hit_heavy", "stance",
	]
