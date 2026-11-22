extends RefCounted
## 《牌拳》角色外观规格：琉音方向（V4-02 设定图）。
##
## 这里只放常量与可自检的规格，**不画任何东西** —— 绘制在
## `fighter.gd::_draw_skin_v2()`。拆开的原因：外观规格要能被纯逻辑自检
## 点名断言，而 CanvasItem 的 draw_* 只能在 _draw() 期间调用。
##
## 阵营色不在这里：仍由 `fighter.gd::palette()` 提供，实时格斗与回合制
## 合战两套骨架共用同一套暖琥珀 / 冷青。这套常量只管「衣服长什么样」。
##
## 造型边界（对齐 V4-02）：黑白「白切黑」+ 红中国结 + 金扣 + 双环发髻，
## 中性全覆盖战斗服，不画露肩 / 露腰 / 肚兜 / 丝袜特写。

const WHITE := Color(0.94, 0.94, 0.91)
const INK := Color(0.11, 0.11, 0.15)
const RED := Color(0.72, 0.15, 0.16)
const GOLD := Color(0.86, 0.68, 0.30)
const SKIN_FACE := Color(0.95, 0.84, 0.74)
const HOLE := Color(0.09, 0.08, 0.11)
const SILVER := Color(0.85, 0.88, 0.92)

const GLOVE_RADIUS := 14.0
const BUN_RADIUS := 9.0
const TORSO_HALF := 24.0
const SHOE_TOP := -14.0

## 每一个名字都对应 `_draw_skin_v2()` 里一段实际画出来的东西。
## 名单同时被断言长度：只断言 has() 会让「悄悄删掉一半部件」通过。
const PARTS := [
	"white_outer", "ink_collar", "red_sash", "gold_clasp",
	"chinese_knot", "double_bun", "pom_pom", "hair_clip",
	"half_lidded_eye", "glove", "platform_shoe", "ring_blade",
]


static func spec() -> Dictionary:
	return {
		"white": WHITE,
		"ink": INK,
		"red": RED,
		"gold": GOLD,
		"skin": SKIN_FACE,
		"glove_radius": GLOVE_RADIUS,
		"bun_radius": BUN_RADIUS,
		"torso_half": TORSO_HALF,
		"parts": PARTS.duplicate(),
	}


static func part_names() -> Array:
	return PARTS.duplicate()
