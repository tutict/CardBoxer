class_name FightHUD
extends Control
## 全部手绘的界面层：血条、气槽、手牌、连招提示、回合点、计时。
##
## 用 SystemFont 而不是默认主题字体：Godot 自带字体没有中文字形，直接写中文
## 会渲染成空心方块。系统字体名按优先级回退，四个里总能命中一个。

const Defs = preload("res://scripts/card_data.gd")

const BAR_W := 452.0
const BAR_H := 24.0
const CARD_W := 148.0
const CARD_H := 150.0
const CARD_GAP := 16.0
const HAND_Y := 552.0

const COL_ATTACK := Color(0.93, 0.36, 0.28)
const COL_MOVE := Color(0.28, 0.76, 0.60)
const COL_GUARD := Color(0.34, 0.60, 0.95)
const COL_POWER := Color(0.70, 0.45, 0.94)

## 血条 V2：与擂台灯光 / 角色 / 回合点统一成暖琥珀（玩家）与冷青（对手）
## 两套色；红色只留给「低血量危险」，不再表示阵营。
const HP_PLAYER_TOP := Color(1.0, 0.80, 0.42)
const HP_PLAYER_BOTTOM := Color(0.72, 0.38, 0.14)
const HP_ENEMY_TOP := Color(0.48, 0.88, 1.0)
const HP_ENEMY_BOTTOM := Color(0.14, 0.44, 0.72)
const HP_DANGER := Color(0.98, 0.24, 0.22)
const HP_GHOST := Color(1.0, 0.58, 0.40, 0.55)

## 这些标点不能出现在行首，折行时跟着上一行走。
const NO_LINE_START := "，。、；：！？）》」』）】%,.;:!?)]}"

var arena: Node = null
var font: SystemFont
var _font_small: SystemFont
var _hp_shown := {"p": 1.0, "e": 1.0}
var _time := 0.0


func _ready() -> void:
	font = SystemFont.new()
	font.font_names = PackedStringArray([
		"Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "sans-serif"
	])
	_font_small = font
	# 父节点是 Node2D，不是 Control，anchors 没有参照物可用，直接给定尺寸。
	size = Vector2(1280, 720)
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func _process(delta: float) -> void:
	_time += delta
	# 血条残影：受击后白色那一截慢慢追上去，让伤害量看得见。
	if arena != null:
		var p: float = arena.player.hp_ratio()
		var e: float = arena.enemy.hp_ratio()
		_hp_shown["p"] = move_toward(float(_hp_shown["p"]), p, delta * 0.35)
		_hp_shown["e"] = move_toward(float(_hp_shown["e"]), e, delta * 0.35)
		if p > float(_hp_shown["p"]):
			_hp_shown["p"] = p
		if e > float(_hp_shown["e"]):
			_hp_shown["e"] = e
	queue_redraw()


func _draw() -> void:
	if arena == null:
		return
	_draw_hud_bars()
	_draw_center()
	_draw_hand()
	_draw_taikou_reveal()
	_draw_banner()
	_draw_hints()


# ── 顶部血条与气槽 ────────────────────────────────────────────

func _draw_hud_bars() -> void:
	var p: Fighter = arena.player
	var e: Fighter = arena.enemy

	# 玩家：从左向右。
	_draw_bar_v2(Vector2(44, 44), p.hp_ratio(), float(_hp_shown["p"]), false, p.display_name, true)
	if arena.battle_mode == "taikou":
		draw_string(
			font, Vector2(44, 104), "第 %d 轮 / 共 %d 轮" % [int(arena.tk_turn), int(arena.TK_MAX_TURNS)],
			HORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color(0.84, 0.89, 0.98)
		)
	else:
		_draw_meter(Vector2(44, 76), p.meter_ratio(), 5)
		draw_string(
			font, Vector2(44, 104), "气 %d/5" % int(p.meter), HORIZONTAL_ALIGNMENT_LEFT, -1, 13,
			Color(0.60, 0.72, 0.88)
		)

	# 对手：镜像。
	_draw_bar_v2(Vector2(1280 - 44 - BAR_W, 44), e.hp_ratio(), float(_hp_shown["e"]), true, e.display_name, false)
	if arena.battle_mode == "taikou":
		var turn_label := "第 %d 轮 / 共 %d 轮" % [int(arena.tk_turn), int(arena.TK_MAX_TURNS)]
		var tl_w := font.get_string_size(turn_label, HORIZONTAL_ALIGNMENT_LEFT, -1, 13).x
		draw_string(
			font, Vector2(1280 - 44 - tl_w, 104), turn_label, HORIZONTAL_ALIGNMENT_LEFT, -1, 15,
			Color(0.84, 0.89, 0.98)
		)
	else:
		_draw_meter(Vector2(1280 - 44 - BAR_W, 76), e.meter_ratio(), 5)
		var meter_label := "气 %d/5" % int(e.meter)
		var ml_w := font.get_string_size(meter_label, HORIZONTAL_ALIGNMENT_LEFT, -1, 13).x
		draw_string(
			font, Vector2(1280 - 44 - ml_w, 104), meter_label, HORIZONTAL_ALIGNMENT_LEFT, -1, 13,
			Color(0.60, 0.72, 0.88)
		)


func _draw_bar(pos: Vector2, ratio: float, ghost: float, mirrored: bool, who: String, is_player: bool) -> void:
	var back := Color(0.08, 0.09, 0.14, 0.92)
	draw_rect(Rect2(pos + Vector2(-3, -3), Vector2(BAR_W + 6, BAR_H + 6)), Color(0, 0, 0, 0.55))
	draw_rect(Rect2(pos, Vector2(BAR_W, BAR_H)), back)

	var ghost_w := BAR_W * ghost
	if mirrored:
		draw_rect(Rect2(pos + Vector2(BAR_W - ghost_w, 0), Vector2(ghost_w, BAR_H)), Color(0.96, 0.94, 0.90, 0.45))

	var w := BAR_W * ratio
	var fill := Color(0.55, 0.86, 0.52) if is_player else Color(0.95, 0.42, 0.40)
	if ratio < 0.3:
		fill = fill.lerp(Color(0.98, 0.22, 0.24), 0.5 + 0.25 * sin(_time * 9.0))
	if mirrored:
		draw_rect(Rect2(pos + Vector2(BAR_W - w, 0), Vector2(w, BAR_H)), fill)
	else:
		draw_rect(Rect2(pos, Vector2(w, BAR_H)), fill)

	# 内高光，让血条不是一块死色。
	draw_rect(Rect2(pos + Vector2(0, 0), Vector2(BAR_W, 5)), Color(1, 1, 1, 0.10))

	var label := "%s  %d" % [who, int(round(ratio * 100.0))]
	var size := 18
	var text_w := font.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x
	var tx := pos.x + BAR_W - text_w if mirrored else pos.x
	draw_string(font, Vector2(tx, pos.y - 8), label, HORIZONTAL_ALIGNMENT_LEFT, -1, size, Color(0.92, 0.94, 1.0))


## 血条 V2。原 _draw_bar() 完整保留作兜底：把 _draw_hud_bars() 里的两处
## 调用换回 _draw_bar 即可回到旧样式，不需要动绘制逻辑。
func _draw_bar_v2(pos: Vector2, ratio: float, ghost: float, mirrored: bool, who: String, is_player: bool) -> void:
	var r := clampf(ratio, 0.0, 1.0)
	var g := clampf(ghost, 0.0, 1.0)

	# 外框 / 背板比旧版更暗，让填充成为画面里唯一的高亮横条。
	draw_rect(Rect2(pos + Vector2(-4, -4), Vector2(BAR_W + 8, BAR_H + 8)), Color(0, 0, 0, 0.48))
	draw_rect(Rect2(pos + Vector2(-1, -1), Vector2(BAR_W + 2, BAR_H + 2)), Color(0.42, 0.40, 0.56, 0.42))
	draw_rect(Rect2(pos, Vector2(BAR_W, BAR_H)), Color(0.055, 0.06, 0.095, 0.95))

	# 残影：刚掉的那一截用统一的伤害橙；白色容易读成「还没扣」。
	if g > 0.0:
		draw_rect(_bar_fill_rect(pos, BAR_W * g, mirrored), HP_GHOST)

	# 填充：6 条横向色带做竖向渐变，不再是一整块死色。
	var w := BAR_W * r
	if w > 0.0:
		var top := HP_PLAYER_TOP if is_player else HP_ENEMY_TOP
		var bottom := HP_PLAYER_BOTTOM if is_player else HP_ENEMY_BOTTOM
		if r < 0.3:
			var pulse := 0.55 + 0.25 * sin(_time * 9.0)
			top = top.lerp(HP_DANGER, pulse)
			bottom = bottom.lerp(HP_DANGER, pulse)
		var origin := (pos.x + BAR_W - w) if mirrored else pos.x
		var bands := 6
		for i in range(bands):
			var t := (float(i) + 0.5) / float(bands)
			draw_rect(
				Rect2(origin, pos.y + BAR_H * float(i) / float(bands), w, BAR_H / float(bands) + 1.0),
				bottom.lerp(top, 1.0 - t)
			)
		# 内高光只覆盖已填充部分，空槽不再发白。
		draw_rect(Rect2(origin, pos.y, w, 2), Color(1, 1, 1, 0.22))
		# 血量指针：填充末端的亮竖线，格斗游戏里读当前血量最省眼。
		var edge_x := origin if mirrored else origin + w
		draw_line(Vector2(edge_x, pos.y), Vector2(edge_x, pos.y + BAR_H), Color(1, 1, 1, 0.75), 2.0)

	# 20 点一格刻度画在最上层：亮填充上是细暗分隔，暗背板上不抢眼。
	for i in range(1, 5):
		var tx := pos.x + BAR_W * float(i) / 5.0
		draw_line(Vector2(tx, pos.y + 1), Vector2(tx, pos.y + BAR_H - 1), Color(0.02, 0.02, 0.06, 0.22), 1.0)

	# 低血量红框脉冲：双方同色，红色只表示危险。
	# 谷值必须留够：旧式 0.35+0.30*sin 最低只有 0.05，引擎内截帧反推到
	# alpha≈0.19 那一帧肉眼几乎看不见红框，危险提示会在脉冲低谷消失。
	# 现在是 0.30..0.80，最暗的一帧也读得出来。
	if r < 0.3:
		draw_rect(
			Rect2(pos + Vector2(-1, -1), Vector2(BAR_W + 2, BAR_H + 2)),
			Color(0.98, 0.24, 0.22, 0.55 + 0.25 * sin(_time * 9.0)), false, 2.0
		)

	# 名字与数值分层次：名字小一档偏灰，数值大一号纯白并带阴影。
	var name_size := 15
	var num_size := 22
	var num_text := str(int(round(r * 100.0)))
	var nw := font.get_string_size(who, HORIZONTAL_ALIGNMENT_LEFT, -1, name_size).x
	var vw := font.get_string_size(num_text, HORIZONTAL_ALIGNMENT_LEFT, -1, num_size).x
	var gap := 10.0
	var x0 := (pos.x + BAR_W - (nw + gap + vw)) if mirrored else pos.x
	draw_string(font, Vector2(x0 + 1, pos.y - 9), who, HORIZONTAL_ALIGNMENT_LEFT, -1, name_size, Color(0, 0, 0, 0.6))
	draw_string(font, Vector2(x0, pos.y - 10), who, HORIZONTAL_ALIGNMENT_LEFT, -1, name_size, Color(0.76, 0.79, 0.90))
	var nx := x0 + nw + gap
	draw_string(font, Vector2(nx + 1, pos.y - 7), num_text, HORIZONTAL_ALIGNMENT_LEFT, -1, num_size, Color(0, 0, 0, 0.65))
	draw_string(font, Vector2(nx, pos.y - 8), num_text, HORIZONTAL_ALIGNMENT_LEFT, -1, num_size, Color(1, 1, 1))


func _bar_fill_rect(pos: Vector2, width: float, mirrored: bool) -> Rect2:
	var x := (pos.x + BAR_W - width) if mirrored else pos.x
	return Rect2(Vector2(x, pos.y), Vector2(width, BAR_H))


func _draw_meter(pos: Vector2, ratio: float, segs: int) -> void:
	var seg_w := (BAR_W - float(segs - 1) * 6.0) / float(segs)
	for i in range(segs):
		var x := pos.x + float(i) * (seg_w + 6.0)
		var slot := Rect2(Vector2(x, pos.y), Vector2(seg_w, 10))
		# 空槽也要看得见：底比血条背板亮一档，再加一条描边。
		draw_rect(slot, Color(0.18, 0.20, 0.29, 0.95))
		draw_rect(slot, Color(0.34, 0.38, 0.52, 0.85), false, 1.0)
		var filled: float = clampf(ratio * float(segs) - float(i), 0.0, 1.0)
		if filled <= 0.0:
			continue
		var color := Color(0.55, 0.80, 0.98)
		if i >= 3:
			color = Color(1.0, 0.82, 0.35)  # 第 4、5 格：放大招的门槛，换个颜色
		draw_rect(Rect2(Vector2(x + 1, pos.y + 1), Vector2((seg_w - 2.0) * filled, 8)), color)


# ── 中央：计时与回合点 ────────────────────────────────────────

func _draw_center() -> void:
	var center := Vector2(640, 52)
	draw_circle(center, 40.0, Color(0.05, 0.06, 0.10, 0.85))
	draw_arc(center, 40.0, 0.0, TAU, 40, Color(0.55, 0.60, 0.78, 0.55), 2.0)
	var secs: int = int(ceil(maxf(0.0, float(arena.round_time_left))))
	var t := "%02d" % secs
	var num_color := Color(0.94, 0.95, 1.0)
	if arena.battle_mode == "taikou":
		t = "%d" % int(arena.tk_turn)
	elif secs <= 10:
		num_color = Color(1.0, 0.28, 0.28)
	var tw := font.get_string_size(t, HORIZONTAL_ALIGNMENT_LEFT, -1, 30).x
	draw_string(
		font, center + Vector2(-tw * 0.5, 11), t, HORIZONTAL_ALIGNMENT_LEFT, -1, 30, num_color
	)

	# 回合点：先到 2 胜。玩家在左、对手在右，与血条同侧。
	for side in range(2):
		var wins: int = arena.round_wins[side]
		for i in range(2):
			var cx := 640.0 - 120.0 - float(i) * 22.0 if side == 0 else 640.0 + 120.0 + float(i) * 22.0
			var filled := i < wins
			var col := Color(0.98, 0.68, 0.30) if side == 0 else Color(0.34, 0.78, 0.96)
			var pos := Vector2(cx, 52)
			draw_circle(pos, 8.0, col if filled else Color(0.34, 0.37, 0.48, 0.95))
			if not filled:
				draw_arc(pos, 8.0, 0.0, TAU, 16, Color(0.52, 0.56, 0.70, 0.9), 1.5)


# ── 手牌 ────────────────────────────────────────────────────

func _draw_hand() -> void:
	var hand: Array = arena.hand
	var total := float(hand.size()) * CARD_W + float(hand.size() - 1) * CARD_GAP
	var x0 := 640.0 - total * 0.5
	for i in range(hand.size()):
		var x := x0 + float(i) * (CARD_W + CARD_GAP)
		var id: Variant = hand[i]
		if id == null:
			_draw_empty_slot(Vector2(x, HAND_Y), i)
			continue
		_draw_card(Vector2(x, HAND_Y), String(id), i, arena.cooldowns[i])


func _draw_card(pos: Vector2, id: String, index: int, cooldown: float) -> void:
	var card := Defs.card(id)
	if card.is_empty():
		return
	var kind := String(card["kind"])
	var accent := _kind_color(kind)
	var cost := int(card["cost"])
	var affordable := true if arena.battle_mode == "taikou" else int(arena.player.meter) >= cost
	var hover := float(arena.selected_index) == float(index)
	var marked: bool = arena.battle_mode == "taikou" and arena.tk_marks.has(index)
	var lift := -22.0 if marked else (-10.0 if hover else 0.0)
	var rect := Rect2(pos + Vector2(0, lift), Vector2(CARD_W, CARD_H))

	draw_rect(Rect2(rect.position + Vector2(3, 5), rect.size), Color(0, 0, 0, 0.45))
	draw_rect(rect, Color(0.10, 0.11, 0.16) if affordable else Color(0.07, 0.07, 0.10))
	draw_rect(Rect2(rect.position, Vector2(rect.size.x, 5)), accent)
	draw_rect(rect, Color(0.30, 0.33, 0.44), false, 1.5)
	if hover:
		draw_rect(rect.grow(3.0), accent, false, 2.0)
	if marked:
		var mark_color := Color(0.98, 0.42, 0.36) if arena.tk_phase == "discard" else Color(0.98, 0.80, 0.36)
		draw_rect(rect.grow(4.0), mark_color, false, 3.0)
		var tag := "换" if arena.tk_phase == "discard" else "出"
		draw_string(
			font, rect.position + Vector2(CARD_W - 30, 52), tag,
			HORIZONTAL_ALIGNMENT_LEFT, -1, 20, mark_color
		)

	# 序号：键盘 1-5 直接出这张。
	draw_circle(rect.position + Vector2(18, 26), 12.0, Color(0.06, 0.07, 0.11, 0.95))
	draw_arc(rect.position + Vector2(18, 26), 12.0, 0.0, TAU, 20, accent, 1.5)
	var num := str(index + 1)
	var nw := font.get_string_size(num, HORIZONTAL_ALIGNMENT_LEFT, -1, 15).x
	draw_string(font, rect.position + Vector2(18 - nw * 0.5, 31), num, HORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color(0.95, 0.95, 1.0))

	# 回合制显示点数 rank（比牌只看它）；实时模式显示气耗。
	if arena.battle_mode == "taikou":
		var rank_text := str(int(card.get("rank", 0)))
		var rw := font.get_string_size(rank_text, HORIZONTAL_ALIGNMENT_LEFT, -1, 30).x
		draw_string(
			font, rect.position + Vector2(CARD_W - rw - 14, 40), rank_text,
			HORIZONTAL_ALIGNMENT_LEFT, -1, 30, Color(1.0, 0.90, 0.62)
		)
	else:
		var cost_text := "%d气" % cost if cost > 0 else "免费"
		draw_string(
			font, rect.position + Vector2(CARD_W - 48, 30), cost_text, HORIZONTAL_ALIGNMENT_LEFT, -1, 14,
			accent if affordable else Color(0.55, 0.30, 0.30)
		)

	# 牌名
	draw_string(
		font, rect.position + Vector2(12, 72), String(card["name"]), HORIZONTAL_ALIGNMENT_LEFT, -1, 25,
		Color(0.96, 0.96, 1.0) if affordable else Color(0.55, 0.56, 0.62)
	)

	# 类型标签
	draw_string(
		font, rect.position + Vector2(12, 96), _kind_label(kind), HORIZONTAL_ALIGNMENT_LEFT, -1, 13, accent
	)

	# 描述：三行截断，卡面上只放最有用的那半句。
	var desc := String(card["text"])
	var lines := _wrap(desc, 12, 118)
	var y := 114.0
	for line: String in lines:
		if y > CARD_H - 6.0:
			break
		draw_string(
			font, rect.position + Vector2(12, y), line, HORIZONTAL_ALIGNMENT_LEFT, -1, 13,
			Color(0.72, 0.74, 0.82)
		)
		y += 15.0

	if cooldown > 0.0:
		var frac: float = clampf(cooldown / arena.cooldown_total, 0.0, 1.0)
		draw_rect(rect, Color(0.02, 0.03, 0.06, 0.62))
		draw_rect(
			Rect2(rect.position + Vector2(0, rect.size.y * (1.0 - frac)), Vector2(rect.size.x, rect.size.y * frac)),
			Color(accent.r, accent.g, accent.b, 0.16)
		)


func _draw_empty_slot(pos: Vector2, index: int) -> void:
	var rect := Rect2(pos, Vector2(CARD_W, CARD_H))
	draw_rect(rect, Color(0.05, 0.06, 0.09, 0.55))
	draw_rect(rect, Color(0.20, 0.22, 0.30), false, 1.0)
	var nw := font.get_string_size(str(index + 1), HORIZONTAL_ALIGNMENT_LEFT, -1, 14).x
	draw_string(
		font, rect.position + Vector2(CARD_W * 0.5 - nw * 0.5, CARD_H * 0.5),
		str(index + 1), HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color(0.28, 0.30, 0.38)
	)



# ── 太阁 IV 合战：亮牌区 ─────────────────────────────────────

func _draw_taikou_reveal() -> void:
	if arena.battle_mode != "taikou":
		return
	if arena.tk_phase != "reveal" and arena.tk_phase != "resolve":
		return
	var y := 132.0
	_draw_reveal_side(Vector2(44, y), arena.tk_player_reveal, arena.tk_player_result, "你", Color(0.98, 0.76, 0.36), false)
	_draw_reveal_side(Vector2(1236, y), arena.tk_enemy_reveal, arena.tk_enemy_result, "青岚", Color(0.42, 0.80, 0.98), true)


func _draw_reveal_side(pos: Vector2, ranks: Array, result: Dictionary, who: String, accent: Color, mirrored: bool) -> void:
	if ranks.is_empty():
		return
	var box_w := 70.0
	var gap := 8.0
	var total := float(ranks.size()) * box_w + float(ranks.size() - 1) * gap
	var x0 := (pos.x - total) if mirrored else pos.x
	draw_string(font, Vector2(x0, pos.y - 8), who, HORIZONTAL_ALIGNMENT_LEFT, -1, 16, accent)

	# 赢的一侧给亮边，输的一侧压暗；平局两边保持中性。
	var own := "player" if not mirrored else "enemy"
	# arena 是 untyped，从它的属性做 := 推不出 bool，必须显式标注。
	var won: bool = arena.tk_winner == own
	var lost: bool = arena.tk_phase == "resolve" and not won and arena.tk_winner != "draw"
	for i in range(ranks.size()):
		var x := x0 + float(i) * (box_w + gap)
		var rect := Rect2(x, pos.y, box_w, 62.0)
		draw_rect(rect, Color(0.09, 0.10, 0.15, 0.95))
		var edge := accent
		if lost:
			edge = Color(0.36, 0.38, 0.46)
		elif won and arena.tk_phase == "resolve":
			edge = Color(1.0, 0.92, 0.62)
		draw_rect(rect, edge, false, 2.0)
		var num := str(int(ranks[i]))
		var nw := font.get_string_size(num, HORIZONTAL_ALIGNMENT_LEFT, -1, 38).x
		draw_string(
			font, Vector2(x + box_w * 0.5 - nw * 0.5, pos.y + 45), num,
			HORIZONTAL_ALIGNMENT_LEFT, -1, 38,
			Color(0.55, 0.57, 0.65) if lost else Color(0.97, 0.97, 1.0)
		)

	var label := String(result.get("name", ""))
	var lw := font.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, 18).x
	var lx := (x0 + total - lw) if mirrored else x0
	draw_string(font, Vector2(lx, pos.y + 84), label, HORIZONTAL_ALIGNMENT_LEFT, -1, 18, accent)



func _draw_banner() -> void:
	if arena.banner_time <= 0.0 or arena.banner_text == "":
		return
	var t: float = arena.banner_time
	var alpha: float = clampf(t / 0.35, 0.0, 1.0)
	var scale_in: float = 1.0 + 0.25 * clampf(t / 0.6, 0.0, 1.0)
	var size := int(46.0 * scale_in)
	var text: String = arena.banner_text
	var tw := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x
	var y := 236.0
	var color: Color = arena.banner_color
	color.a = alpha
	draw_string(font, Vector2(640 - tw * 0.5 + 2, y + 2), text, HORIZONTAL_ALIGNMENT_LEFT, -1, size, Color(0, 0, 0, alpha * 0.6))
	draw_string(font, Vector2(640 - tw * 0.5, y), text, HORIZONTAL_ALIGNMENT_LEFT, -1, size, color)

	if arena.banner_sub != "":
		var sw := font.get_string_size(arena.banner_sub, HORIZONTAL_ALIGNMENT_LEFT, -1, 17).x
		draw_string(
			font, Vector2(640 - sw * 0.5, y + 30), arena.banner_sub, HORIZONTAL_ALIGNMENT_LEFT, -1, 17,
			Color(0.85, 0.87, 0.94, alpha)
		)


# ── 底部提示 ────────────────────────────────────────────────

func _draw_hints() -> void:
	var hint := "1-5 出牌    A/D 或 ←/→ 移动    R 重开    空格 暂停"
	if arena.battle_mode == "taikou":
		match arena.tk_phase:
			"discard":
				hint = "弃牌：1-5 标记要换的牌（最多 3 张，可不换）   空格确认   R 重开   P 暂停"
			"select":
				hint = "选牌：1-5 选 3 张凑牌型   空格亮牌   R 重开   P 暂停"
			"reveal":
				hint = "比牌：三同 > 三连 > 散牌   111 最大 · 123 最大 · 同张恒压连张"
			"resolve":
				hint = "结算：牌型底数 + 点数和零头"
			_:
				hint = "回合制合战"
	draw_string(font, Vector2(44, 712), hint, HORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color(0.62, 0.66, 0.78))

	if arena.combo_shown > 0 and arena.battle_mode != "taikou":
		var text := "%d 连击" % arena.combo_count
		var size := 26
		var tw := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x
		var alpha: float = clampf(arena.combo_shown / 0.5, 0.0, 1.0)
		draw_string(
			font, Vector2(1266 - tw, 620), text, HORIZONTAL_ALIGNMENT_LEFT, -1, size,
			Color(1.0, 0.86, 0.42, alpha)
		)

	if arena.paused:
		draw_rect(Rect2(0, 0, 1280, 720), Color(0.02, 0.03, 0.06, 0.55))
		var p := "暂停"
		var pw := font.get_string_size(p, HORIZONTAL_ALIGNMENT_LEFT, -1, 64).x
		draw_string(font, Vector2(640 - pw * 0.5, 380), p, HORIZONTAL_ALIGNMENT_LEFT, -1, 64, Color(0.95, 0.96, 1.0))


# ── 小工具 ──────────────────────────────────────────────────

func _kind_color(kind: String) -> Color:
	match kind:
		Defs.KIND_ATTACK:
			return COL_ATTACK
		Defs.KIND_MOVE:
			return COL_MOVE
		Defs.KIND_GUARD:
			return COL_GUARD
		_:
			return COL_POWER


func _kind_label(kind: String) -> String:
	match kind:
		Defs.KIND_ATTACK:
			return "进攻"
		Defs.KIND_MOVE:
			return "位移"
		Defs.KIND_GUARD:
			return "守御"
		_:
			return "蓄力"


## 按字宽硬折行。中文没有空格可断，只能逐字量；行首压到的标点跟着上一行走。
func _wrap(text: String, per_line: int, _width: float) -> Array:
	var out: Array = []
	var line := ""
	var i := 0
	while i < text.length():
		line += text[i]
		i += 1
		if line.length() >= per_line:
			while i < text.length() and NO_LINE_START.contains(text[i]):
				line += text[i]
				i += 1
			out.append(line)
			line = ""
	if line != "":
		out.append(line)
	return out
