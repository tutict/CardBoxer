class_name Fighter
extends Node2D
## 一名拳手：状态机 + 卡牌结算 + 自绘。
##
## 没有任何贴图。姿态由关节坐标算出来，_draw 里画成剪影。这样做不是因为
## 好看，是因为这段代码要能在没有美术管线的机器上跑起来 —— 流水线给出的
## asset_needs 里有 9 项资产需求，但 Blender 那一步在没有确认的情况下不会
## 执行，灰盒是默认交付形态。既然要灰盒，就把灰盒画到能看清招式。

signal projectile_requested(origin: Vector2, damage: int, direction: int, owner_name: String)
signal hit_confirmed(attacker_is_player: bool, damage: int, blocked: bool, dodged: bool)
signal super_confirmed(card_name: String, owner_is_player: bool)
signal card_played(card_id: String, owner_is_player: bool)

enum State { IDLE, ACTION, HITSTUN, BLOCKSTUN, DODGE, KO }

const Defs = preload("res://scripts/card_data.gd")

const GROUND_Y := 520.0
const ARENA_MIN := 150.0
const ARENA_MAX := 1130.0
const WALK_SPEED := 215.0
const MAX_HP := 100
const MAX_METER := 5

#: 玩家暖琥珀，对手冷青。两个色系在色相上对开，缩到 480p 也能分清谁是谁。
const PALETTE_PLAYER := {
	"main": Color(0.98, 0.66, 0.29),
	"dark": Color(0.52, 0.30, 0.13),
	"trim": Color(1.0, 0.88, 0.62),
}
const PALETTE_ENEMY := {
	"main": Color(0.34, 0.79, 0.96),
	"dark": Color(0.13, 0.35, 0.52),
	"trim": Color(0.78, 0.96, 1.0),
}

var is_player := true
var facing := 1
var hp := MAX_HP
var meter := 0.0
var state := State.IDLE
var state_time := 0.0
var opponent: Fighter = null
var display_name := "拳手"

var _action: Dictionary = {}
var _action_phase := ""
var _phase_time := 0.0
var _has_hit := false
var _combo_bonus := 0
var _combo_name := ""
var _combo_extra := ""
var _is_super := false
var _history: Array = []
#: 连招窗口要一个不会被状态机重置的时钟。用 state_time 的话，出牌时它归零，
#: 上一次的记录时间反而比现在还大，隔了几十秒的牌也会被判成连段。
var _clock := 0.0
var _dodge_bonus := false
var _flash := 0.0
var _walk_time := 0.0
var _moving := 0.0
var _hitstop := 0.0
var _breath := 0.0

# 硬直/受击姿态
var _stun_tilt := 0.0
var _guard_hold := 0.0
var _sidestep_offset := 0.0
var _sidestep_time := 0.0
var _ko_time := 0.0


func _ready() -> void:
	position.y = GROUND_Y


func palette() -> Dictionary:
	return PALETTE_PLAYER if is_player else PALETTE_ENEMY


func reset_for_round(spawn_x: float, face: int) -> void:
	position = Vector2(spawn_x, GROUND_Y)
	facing = face
	hp = MAX_HP
	meter = 0.0
	state = State.IDLE
	state_time = 0.0
	_action = {}
	_action_phase = ""
	_phase_time = 0.0
	_has_hit = false
	_combo_bonus = 0
	_combo_name = ""
	_combo_extra = ""
	_is_super = false
	_history.clear()
	_dodge_bonus = false
	_flash = 0.0
	_stun_tilt = 0.0
	_guard_hold = 0.0
	_sidestep_offset = 0.0
	_ko_time = 0.0
	queue_redraw()


func can_act() -> bool:
	return state == State.IDLE and hp > 0


func hp_ratio() -> float:
	return clampf(float(hp) / float(MAX_HP), 0.0, 1.0)


func meter_ratio() -> float:
	return clampf(meter / float(MAX_METER), 0.0, 1.0)


func add_meter(amount: float) -> void:
	meter = clampf(meter + amount, 0.0, float(MAX_METER))


func active_card() -> Dictionary:
	return _action


## 打出 id 指定的牌。返回是否真的出招（气不够/不可行动时返回 false）。
func play_card(id: String) -> bool:
	if not can_act():
		return false
	var card: Dictionary = Defs.card(id)
	if card.is_empty():
		return false
	var cost: int = int(card.get("cost", 0))
	if cost > int(meter):
		return false

	meter -= float(cost)
	_history = _history.filter(func(entry: Dictionary) -> bool:
		return _clock - float(entry["at"]) <= Defs.COMBO_WINDOW
	)
	_history.append({"id": id, "at": _clock})
	_resolve_combo(id, cost)

	_action = card.duplicate()
	_action["id"] = id
	_is_super = _combo_extra == "super"
	_action_phase = "windup"
	_phase_time = 0.0
	_has_hit = false
	state = State.ACTION
	state_time = 0.0
	card_played.emit(id, is_player)

	if card.get("kind", "") == Defs.KIND_GUARD:
		if id == "guard":
			_guard_hold = 0.55
		elif id == "sidestep":
			_sidestep_time = 0.18
			_sidestep_offset = 0.0
	return true


func _resolve_combo(current_id: String, current_cost: int) -> void:
	_combo_bonus = 0
	_combo_name = ""
	_combo_extra = ""
	var ids: Array = _history.map(func(entry: Dictionary) -> String: return String(entry["id"]))
	# 当前这张的气已经扣掉了，判断大招门槛时要把它的花费加回去。
	var spendable: int = int(meter) + current_cost

	# 先试大招（序列更长，且要扣气），再试普通连招。都取最长匹配。
	for entry: Dictionary in Defs.SUPERS:
		var seq: Array = entry["seq"]
		if _tail_matches(ids, seq) and spendable >= int(entry.get("cost", 0)):
			meter -= float(entry.get("cost", 0))
			_combo_bonus = int(entry["bonus"])
			_combo_name = String(entry["name"])
			_combo_extra = String(entry.get("extra", ""))
			return

	var best: Dictionary = {}
	for entry: Dictionary in Defs.COMBOS:
		var seq: Array = entry["seq"]
		if _tail_matches(ids, seq):
			if best.is_empty() or seq.size() > (best["seq"] as Array).size():
				best = entry
	if not best.is_empty():
		_combo_bonus = int(best["bonus"])
		_combo_name = String(best["name"])
		_combo_extra = String(best.get("extra", ""))


func _tail_matches(ids: Array, seq: Array) -> bool:
	if ids.size() < seq.size():
		return false
	var offset := ids.size() - seq.size()
	for i in range(seq.size()):
		if String(ids[offset + i]) != String(seq[i]):
			return false
	return true


## 由 arena 每帧调用。`move` 是 -1/0/1（只在 IDLE 时生效）。
func tick(delta: float, move: float, can_move: bool) -> void:
	if _hitstop > 0.0:
		_hitstop -= delta
		queue_redraw()
		return

	_breath += delta
	_clock += delta
	_flash = maxf(0.0, _flash - delta * 9.0)
	if _guard_hold > 0.0:
		_guard_hold = maxf(0.0, _guard_hold - delta)
	if _sidestep_time > 0.0:
		_sidestep_time = maxf(0.0, _sidestep_time - delta)
		_sidestep_offset = lerpf(_sidestep_offset, 0.0, delta * 12.0)

	state_time += delta

	match state:
		State.KO:
			_ko_time += delta
		State.HITSTUN, State.BLOCKSTUN:
			if state_time >= _stun_duration:
				state = State.IDLE
				state_time = 0.0
				_stun_tilt = 0.0
		State.ACTION:
			_tick_action(delta)
		State.IDLE, State.DODGE:
			_moving = move if can_move else 0.0
			if _moving != 0.0:
				_walk_time += delta
				position.x = clampf(
					position.x + _moving * WALK_SPEED * delta, ARENA_MIN, ARENA_MAX
				)
			else:
				_walk_time = 0.0
			if state == State.DODGE and state_time > 0.25:
				state = State.IDLE

	queue_redraw()


var _stun_duration := 0.3


func _tick_action(delta: float) -> void:
	_phase_time += delta
	var card := _action
	var windup := float(card.get("windup", 4)) * Defs.FRAME
	var active := float(card.get("active", 3)) * Defs.FRAME
	var recover := float(card.get("recover", 8)) * Defs.FRAME

	match _action_phase:
		"windup":
			if _phase_time >= windup:
				_phase_time = 0.0
				_action_phase = "active"
				_on_active_start()
		"active":
			_resolve_active_hit()
			if _phase_time >= active or active <= 0.0:
				if _action_phase == "active":
					_phase_time = 0.0
					_action_phase = "recover"
		"recover":
			if _phase_time >= recover:
				_end_action()


func _on_active_start() -> void:
	var card := _action
	var id := String(card.get("id", ""))
	var kind := String(card.get("kind", ""))

	# 位移牌必须真的挪人。只画个冲的姿势而位置不变，玩家会以为牌坏了 ——
	# 而且突进原本是用来解决「够不着」的，不挪就等于没有这张牌。
	if kind == Defs.KIND_MOVE:
		var push := 172.0 if id == "rush" else -152.0
		position.x = clampf(position.x + push * float(facing), ARENA_MIN, ARENA_MAX)
	elif id == "sidestep":
		position.x = clampf(position.x - 66.0 * float(facing), ARENA_MIN, ARENA_MAX)

	if kind == Defs.KIND_ATTACK and bool(card.get("bullet", false)):
		var origin := position + Vector2(56.0 * facing, -118.0)
		projectile_requested.emit(
			origin, int(card.get("damage", 0)) + _combo_bonus, facing, display_name
		)


func _resolve_active_hit() -> void:
	var card := _action
	if String(card.get("kind", "")) != Defs.KIND_ATTACK:
		return
	if bool(card.get("bullet", false)):
		return
	if _has_hit or opponent == null:
		return
	var reach := float(card.get("reach", 100))
	var dx: float = absf(opponent.position.x - position.x)
	# 必须面向对手：背身打不到。
	var toward: float = signf(opponent.position.x - position.x)
	if toward != float(facing) and dx > 12.0:
		return
	if dx <= reach:
		_has_hit = true
		var damage: int = int(card.get("damage", 0)) + _combo_bonus
		if String(card["id"]) == "cross" and opponent.is_attacking():
			damage *= 2
		if _dodge_bonus:
			damage += 3
			_dodge_bonus = false
		apply_hit(damage, String(card["id"]), _combo_extra, _is_super)


func is_attacking() -> bool:
	return state == State.ACTION and _action_phase != "recover"


## 刚打出的这张牌结算出了什么连招（空串表示只是单招）。
func combo_name() -> String:
	return _combo_name


func combo_bonus() -> int:
	return _combo_bonus


## 前摇中。AI 靠这个决定「现在防还是现在换血」——它是唯一能读出对手要出招的窗口。
func is_winding_up() -> bool:
	return state == State.ACTION and _action_phase == "windup"


## 出招后摇中。对手读这个来决定要不要惩罚。
func is_recovering() -> bool:
	return state == State.ACTION and _action_phase == "recover"


func is_guarding() -> bool:
	return state == State.ACTION and _guard_hold > 0.0


func is_invulnerable() -> bool:
	return state == State.DODGE or _sidestep_time > 0.0


## 被对手打中。返回是否真的造成了伤害。
func apply_hit(damage: int, card_id: String, extra: String, is_super: bool) -> bool:
	if hp <= 0:
		return false

	if is_invulnerable():
		# 闪避成功也要出声：否则玩家分不清「他打空了」和「我根本没按对」。
		hit_confirmed.emit(not is_player, 0, false, true)
		return false

	var blocked := is_guarding() and card_id != "throw"
	if blocked:
		var reduced: int = maxi(1, int(round(float(damage) * 0.2)))
		hp = maxi(0, hp - reduced)
		_flash = 1.0
		_hitstop = 0.06
		state = State.BLOCKSTUN
		state_time = 0.0
		_stun_duration = 0.16
		_stun_tilt = 0.25 * float(-facing)
		add_meter(0.4)
		hit_confirmed.emit(not is_player, reduced, true, false)
		_check_ko()
		return true

	hp = maxi(0, hp - damage)
	_flash = 1.0
	_hitstop = 0.085 if not is_super else 0.22
	state = State.HITSTUN
	state_time = 0.0
	_stun_duration = 0.26
	_stun_tilt = 0.55 * float(-facing)
	if extra == "launch":
		_stun_duration = 0.42
		_stun_tilt = 0.9 * float(-facing)
	elif extra == "stagger":
		_stun_duration = 0.5
		_stun_tilt = 0.7 * float(-facing)
	elif extra == "super":
		_stun_duration = 0.75
		_stun_tilt = 1.2 * float(-facing)
		add_meter(0.5)
	add_meter(0.6)
	hit_confirmed.emit(not is_player, damage, false, false)
	if is_super:
		super_confirmed.emit(combo_name(), not is_player)
	_check_ko()
	return true


func _check_ko() -> void:
	if hp <= 0:
		state = State.KO
		state_time = 0.0
		_ko_time = 0.0


func on_dodged_successfully() -> void:
	_dodge_bonus = true


func _end_action() -> void:
	_action = {}
	_action_phase = ""
	_phase_time = 0.0
	state = State.IDLE
	state_time = 0.0


## 让 arena 在回合结束时停手。
func freeze() -> void:
	_action = {}
	_action_phase = ""
	state = State.IDLE if hp > 0 else State.KO


func face_toward(other_x: float) -> void:
	if state == State.ACTION or state == State.HITSTUN:
		return
	if absf(other_x - position.x) < 4.0:
		return
	facing = 1 if other_x > position.x else -1


# ─────────────────────────────────────────────────────────────
# 自绘：关节坐标 → 剪影
# ────────────────────────────────────────────────-------------

var _pose_cache: Dictionary = {}


func _draw() -> void:
	var pal := palette()
	var main: Color = pal["main"]
	var dark: Color = pal["dark"]
	var trim: Color = pal["trim"]

	_draw_shadow()

	# 气满时的一圈辉光：让"能放大了"在角色身上直接可见，不用看 UI。
	if meter >= 3.0:
		var glow := Color(trim.r, trim.g, trim.b, 0.06 + 0.05 * sin(_breath * 4.0))
		draw_circle(Vector2(0, -95), 96.0 + 6.0 * sin(_breath * 3.0), glow)

	var p := _build_pose()
	var flash_mix: float = clampf(_flash, 0.0, 1.0)
	# 0.55 上限：再高受击者就整块变白，分不清是谁挨了打。
	var body := main.lerp(Color(1, 1, 1), flash_mix * 0.55)
	var limb := dark.lerp(Color(1, 1, 1), flash_mix * 0.45)

	# 后侧肢体先画，压暗，制造前后层次。
	_draw_limb(p["shoulder"], p["b_elbow"], limb.darkened(0.18), 11.0)
	_draw_limb(p["b_elbow"], p["b_hand"], limb.darkened(0.18), 10.0)
	_draw_glove(p["b_hand"], limb.darkened(0.3), trim.darkened(0.3))
	_draw_limb(p["hip"], p["b_knee"], limb.darkened(0.12), 14.0)
	_draw_limb(p["b_knee"], p["b_foot"], limb.darkened(0.12), 12.0)
	_draw_foot(p["b_foot"], limb.darkened(0.2))

	_draw_torso(p, body)
	_draw_limb(p["hip"], p["f_knee"], limb, 15.0)
	_draw_limb(p["f_knee"], p["f_foot"], limb, 13.0)
	_draw_foot(p["f_foot"], limb.darkened(0.05))
	_draw_limb(p["shoulder"], p["f_elbow"], body, 12.0)
	_draw_limb(p["f_elbow"], p["f_hand"], body, 11.0)
	_draw_glove(p["f_hand"], body, trim)
	_draw_head(p, body, trim)

	if is_guarding():
		var guard_color := Color(trim.r, trim.g, trim.b, 0.35 + 0.2 * sin(_breath * 12.0))
		draw_arc(Vector2(0, -110), 62.0, -1.1, 1.1, 18, guard_color, 3.0)
	if _sidestep_time > 0.0:
		var ghost := Color(trim.r, trim.g, trim.b, 0.22)
		draw_circle(Vector2(0, -90), 46.0, ghost)


func _draw_shadow() -> void:
	# 影子随受击姿态抖动，落地感来自它而不是角色本身。
	var spread := 46.0 + 8.0 * absf(_stun_tilt)
	draw_set_transform(Vector2(0, 2), 0.0, Vector2(1.0, 0.32))
	draw_circle(Vector2(0, 0), spread, Color(0, 0, 0, 0.35))
	draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)


func _draw_limb(a: Vector2, b: Vector2, color: Color, width: float) -> void:
	# 先描一圈更深的同色系轮廓：在暗背景上把四肢的边立起来，而不是让它们糊成一团。
	draw_line(a, b, color.darkened(0.55), width + 5.0, true)
	draw_line(a, b, color, width, true)
	draw_circle(b, width * 0.5, color)


## 拳套：外圈亮色 + 内芯本色，比一个圆点更像手。
func _draw_glove(at: Vector2, base: Color, trim: Color) -> void:
	draw_circle(at, 11.0, trim.darkened(0.35))
	draw_circle(at, 9.0, trim)
	draw_circle(at, 6.0, base)


func _draw_foot(at: Vector2, color: Color) -> void:
	draw_set_transform(at, 0.0, Vector2(1.0, 0.42))
	draw_circle(Vector2.ZERO, 18.0, color.darkened(0.5))
	draw_circle(Vector2.ZERO, 16.0, color)
	draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)


func _draw_torso(p: Dictionary, color: Color) -> void:
	var hip: Vector2 = p["hip"]
	var shoulder: Vector2 = p["shoulder"]
	var lean: float = p["lean"]
	var dir := Vector2(lean, 0.0)

	var chest := PackedVector2Array([
		hip + Vector2(-20, 4),
		shoulder + Vector2(-26, 2),
		shoulder + Vector2(24, 0) + dir,
		hip + Vector2(20, 2),
	])
	draw_colored_polygon(chest, color)

	# 腰带：一条深色横线，给剪影一个可读的水平参照。
	draw_line(
		hip + Vector2(-20, -2) + dir * 0.4,
		hip + Vector2(20, -2) + dir * 0.4,
		Color(0.08, 0.08, 0.12, 0.85),
		6.0,
		true
	)


func _draw_head(p: Dictionary, color: Color, trim: Color) -> void:
	var head: Vector2 = p["head"]
	var radius := 20.0
	draw_circle(head, radius, color)
	# 面部朝前的一小块高光，代替五官，远看也能读出朝向。
	var eye := head + Vector2(9.0 * float(facing), -3.0)
	draw_circle(eye, 4.2, trim)
	draw_line(
		head + Vector2(-6.0 * float(facing), -12.0),
		head + Vector2(10.0 * float(facing), -14.0),
		Color(trim.r, trim.g, trim.b, 0.7) if is_player else Color(0.05, 0.12, 0.18, 0.9),
		3.0,
		true
	)


func _build_pose() -> Dictionary:
	var f := float(facing)
	var breathe := sin(_breath * 2.4) * 3.0
	var bob := sin(_walk_time * 9.0) * 5.0 if _moving != 0.0 else 0.0
	var hip := Vector2(0, -92 + breathe + bob)
	var shoulder := Vector2(0, -160 + breathe + bob)
	var head := Vector2(2.0 * f, -184 + breathe + bob)
	var lean := 0.0

	# 站姿默认关节
	var f_elbow := Vector2(30.0 * f, -140.0 + breathe)
	var f_hand := Vector2(48.0 * f, -122.0 + breathe)
	var b_elbow := Vector2(-14.0 * f, -138.0 + breathe)
	var b_hand := Vector2(-2.0 * f, -112.0 + breathe)
	var f_knee := Vector2(20.0 * f, -46.0)
	var f_foot := Vector2(30.0 * f, 0.0)
	var b_knee := Vector2(-18.0 * f, -46.0)
	var b_foot := Vector2(-34.0 * f, 0.0)

	# 走路：前后腿交替摆，手臂反向摆。
	if _moving != 0.0:
		var swing := sin(_walk_time * 9.0)
		f_knee += Vector2(18.0 * swing * f, 0)
		f_foot += Vector2(26.0 * swing * f, 0)
		b_knee -= Vector2(14.0 * swing * f, 0)
		b_foot -= Vector2(20.0 * swing * f, 0)
		f_hand += Vector2(-6.0 * swing * f, 6.0 * absf(swing))
		b_hand += Vector2(8.0 * swing * f, 6.0 * absf(swing))

	# 受击：整个上身向后倒。
	if state == State.HITSTUN or state == State.BLOCKSTUN or state == State.KO:
		var tilt := _stun_tilt
		if state == State.KO:
			tilt = minf(1.5, 0.9 + _ko_time * 1.2)
		hip += Vector2(-24.0 * tilt * f, 0)
		shoulder += Vector2(-52.0 * tilt * f, 18.0 * tilt)
		head += Vector2(-66.0 * tilt * f, 30.0 * tilt)
		f_elbow += Vector2(-52.0 * tilt * f, 22.0 * tilt)
		f_hand += Vector2(-70.0 * tilt * f, 34.0 * tilt)
		b_elbow += Vector2(-36.0 * tilt * f, 18.0 * tilt)
		b_hand += Vector2(-50.0 * tilt * f, 28.0 * tilt)
		lean = -0.4 * tilt * f

	# 出招：按招式类型改写关节。
	if state == State.ACTION:
		var card := _action
		var id := String(card.get("id", ""))
		var kind := String(card.get("kind", ""))
		var phase := _action_phase
		var progress := _phase_progress(card)
		var swing := _swing_curve(phase, progress)

		if kind == Defs.KIND_GUARD and id == "guard":
			f_elbow = Vector2(20.0 * f, -150.0)
			f_hand = Vector2(6.0 * f, -176.0)
			b_elbow = Vector2(10.0 * f, -142.0)
			b_hand = Vector2(24.0 * f, -168.0)
			shoulder += Vector2(-4.0 * f, 4.0)
			lean = -0.15 * f
		elif kind == Defs.KIND_GUARD and id == "sidestep":
			var off := sin(progress * PI) * 66.0
			_sidestep_offset = off
			hip += Vector2(-24.0 * f, -10.0)
			shoulder += Vector2(-30.0 * f, -8.0)
			head += Vector2(-34.0 * f, -8.0)
			f_knee += Vector2(-10.0 * f, 0)
			b_hand += Vector2(-16.0 * f, -18.0)
			lean = -0.3 * f
		elif kind == Defs.KIND_POWER and id == "focus":
			hip += Vector2(0, 10.0 * swing)
			shoulder += Vector2(0, 6.0 * swing)
			f_elbow = Vector2(34.0 * f, -120.0)
			f_hand = Vector2(46.0 * f, -92.0)
			b_elbow = Vector2(-30.0 * f, -120.0)
			b_hand = Vector2(-42.0 * f, -92.0)
			lean = 0.0
		elif kind == Defs.KIND_POWER:
			f_hand = Vector2(30.0 * f, -150.0)
			b_hand = Vector2(-10.0 * f, -140.0)
		elif kind == Defs.KIND_MOVE:
			var push := 1.0 if id == "rush" else -1.0
			hip += Vector2(16.0 * push * f * swing, 6.0 * swing)
			shoulder += Vector2(20.0 * push * f * swing, 2.0 * swing)
			head += Vector2(24.0 * push * f * swing, 0)
			f_knee += Vector2(20.0 * push * f * swing, 0)
			b_knee -= Vector2(10.0 * push * f * swing, 0)
			b_foot -= Vector2(16.0 * push * f * swing, 0)
			lean = 0.3 * push * f * swing
		elif id == "uppercut":
			# 下蹲蓄力 → 上勾，重心整体抬高。
			var lift := swing * 26.0
			f_hand = Vector2(34.0 * f, -196.0 + swing * 42.0)
			f_elbow = Vector2(22.0 * f, -160.0 + swing * 18.0)
			b_hand = Vector2(-8.0 * f, -120.0)
			hip += Vector2(6.0 * f * swing, -lift * 0.4)
			shoulder += Vector2(10.0 * f * swing, -lift)
			head += Vector2(12.0 * f * swing, -lift)
			f_knee += Vector2(4.0 * f, -8.0 * swing)
			b_knee += Vector2(-4.0 * f, -4.0 * swing)
			lean = 0.25 * f * swing
		elif id == "sweep":
			# 低扫：一条腿扫出去，上身压低。
			f_knee = Vector2(46.0 * f * swing, -34.0)
			f_foot = Vector2(96.0 * f * swing, -6.0)
			hip += Vector2(-8.0 * f, 18.0 * swing)
			shoulder += Vector2(-14.0 * f, 12.0 * swing)
			head += Vector2(-18.0 * f, 10.0 * swing)
			b_hand = Vector2(-30.0 * f, -96.0)
			lean = -0.2 * f
		elif id == "throw":
			f_hand = Vector2(66.0 * f * swing, -132.0 - 12.0 * swing)
			f_elbow = Vector2(38.0 * f, -146.0)
			b_hand = Vector2(52.0 * f * swing, -118.0)
			b_elbow = Vector2(24.0 * f, -150.0)
			shoulder += Vector2(12.0 * f * swing, 0)
			lean = 0.35 * f * swing
		elif id == "wave":
			# 双手前推，掌间留出能量。
			f_hand = Vector2(62.0 * f, -128.0 - 6.0 * swing)
			f_elbow = Vector2(34.0 * f, -140.0)
			b_hand = Vector2(48.0 * f, -120.0)
			b_elbow = Vector2(22.0 * f, -138.0)
			hip += Vector2(-10.0 * f * swing, 0)
			shoulder += Vector2(8.0 * f * swing, 0)
			lean = 0.18 * f * swing
		else:
			# 刺拳 / 交叉反击：前手直出。
			var reach := 82.0 * swing
			f_hand = Vector2((48.0 + reach) * f, -132.0)
			f_elbow = Vector2((30.0 + reach * 0.45) * f, -140.0)
			b_hand = Vector2(4.0 * f, -116.0)
			b_elbow = Vector2(-8.0 * f, -136.0)
			shoulder += Vector2(14.0 * f * swing, 0)
			hip += Vector2(8.0 * f * swing, 0)
			head += Vector2(10.0 * f * swing, 0)
			lean = 0.22 * f * swing
			f_knee += Vector2(6.0 * f * swing, 0)

	# 侧闪的整体平移
	if _sidestep_offset > 0.0:
		hip.x += _sidestep_offset * -f
		shoulder.x += _sidestep_offset * -f
		head.x += _sidestep_offset * -f
		f_elbow.x += _sidestep_offset * -f
		f_hand.x += _sidestep_offset * -f
		b_elbow.x += _sidestep_offset * -f
		b_hand.x += _sidestep_offset * -f
		f_knee.x += _sidestep_offset * -0.4 * f
		b_knee.x += _sidestep_offset * -0.4 * f

	return {
		"hip": hip,
		"shoulder": shoulder,
		"head": head,
		"f_elbow": f_elbow,
		"f_hand": f_hand,
		"b_elbow": b_elbow,
		"b_hand": b_hand,
		"f_knee": f_knee,
		"f_foot": f_foot,
		"b_knee": b_knee,
		"b_foot": b_foot,
		"lean": lean,
	}


func _phase_progress(card: Dictionary) -> float:
	var span := 0.0
	match _action_phase:
		"windup":
			span = float(card.get("windup", 4)) * Defs.FRAME
		"active":
			span = maxf(float(card.get("active", 3)) * Defs.FRAME, 0.02)
		_:
			span = maxf(float(card.get("recover", 8)) * Defs.FRAME, 0.02)
	return clampf(_phase_time / span, 0.0, 1.0)


## windup 时收势（0→-0.35），active 时甩出（→1），recover 收回（→0）。
func _swing_curve(phase: String, t: float) -> float:
	match phase:
		"windup":
			return -0.35 * t
		"active":
			return 1.0 - pow(1.0 - t, 2.0)
		_:
			return maxf(0.0, 1.0 - t)
	return 0.0
