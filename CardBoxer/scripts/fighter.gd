class_name Fighter
extends Node2D
## 一名拳手：状态机、卡牌结算与原生 3D 演出的只读状态桥。
## 本节点只画地面影子；角色模型由 Fighter3DLayer 绘制。

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
## 原生 3D 步态与实际移动距离同步。
const WALK_STRIDE := 120.0
const WALK_BLEND_RATE := 9.0
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
var _action_seq := 0
var _terminal_snapshot: Dictionary = {}
var _presentation_moving := false
var _presentation_walk_blend := 0.0
var _presentation_walk_direction := 1
var _action_phase := ""
var _phase_time := 0.0
var _has_hit := false
## 回合制合战：只播招式动画，不跑实时命中结算（伤害由 arena 统一结算）。
var _visual_only := false
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
## KOF 式命中节奏的**纯绘制层**位移/倾角。只由 arena._apply_rhythm_visuals()
## 写，只在 _draw() 的 draw_set_transform 里读；position / tick / apply_hit /
## 原生 3D 演出读取视觉偏移，判定语义完全不变。
var visual_shift := Vector2.ZERO
var visual_tilt := 0.0
## 走路姿势的权重 0..1。走路时脚要收到走路的位置、髋要沉下去，直接切会跳一帧。
var _walk_blend := 0.0
var _moving := 0.0
var _hitstop := 0.0
var _breath := 0.0

# 硬直/受击姿态
var _stun_tilt := 0.0
var _guard_hold := 0.0
var _sidestep_time := 0.0
## 位移牌的剩余距离与剩余帧数；见 _begin_slide()。
var _slide_left := 0.0
var _slide_frames := 0
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
	_visual_only = false
	_combo_bonus = 0
	_combo_name = ""
	_combo_extra = ""
	_is_super = false
	_history.clear()
	_dodge_bonus = false
	_flash = 0.0
	_stun_tilt = 0.0
	_guard_hold = 0.0
	_ko_time = 0.0
	_action_seq = 0
	_terminal_snapshot.clear()
	_hitstop = 0.0
	_walk_time = 0.0
	_walk_blend = 0.0
	_moving = 0.0
	_presentation_moving = false
	_presentation_walk_blend = 0.0
	_presentation_walk_direction = 1
	_sidestep_time = 0.0
	visual_shift = Vector2.ZERO
	visual_tilt = 0.0
	_clear_slide()
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


## Authoritative tactical HP is mirrored; this bridge never calls apply_hit,
## emits realtime combat signals, or advances realtime hit/projectile logic.
func present_tactical(snapshot: Dictionary, delta: float) -> void:
	hp = int(snapshot.hp)
	_visual_only = true
	_has_hit = true
	_is_super = false
	_clear_slide()
	state = int(snapshot.state)
	state_time = float(snapshot.state_time)
	if state == State.KO:
		_ko_time = state_time
	_stun_duration = float(snapshot.stun_duration)
	_stun_tilt = float(snapshot.stun_tilt)
	_flash = float(snapshot.flash)
	_hitstop = 0.0
	_action_seq = int(snapshot.action_seq)
	_guard_hold = 0.2 if bool(snapshot.guarding) else 0.0
	_sidestep_time = 0.2 if bool(snapshot.dodging) else 0.0
	_presentation_moving = false
	_presentation_walk_blend = 0.0
	_moving = 0.0
	_walk_blend = 0.0
	if not bool(snapshot.frozen):
		_breath += delta
	if state == State.ACTION:
		var clip := String(snapshot.card_id)
		if String(_action.get("id","")) != clip:
			_action = Defs.card(clip).duplicate()
			_action["id"] = clip
		_action_phase = String(snapshot.phase)
		_phase_time = float(snapshot.phase_progress)*float(_action.get(_action_phase,0))*Defs.FRAME
	else:
		_action.clear()
		_action_phase = ""
		_phase_time = 0.0
	visual_shift = snapshot.canvas_shift
	visual_tilt = float(snapshot.canvas_tilt)
	queue_redraw()


## Read-only bridge: action clocks belong to gameplay; the native controller samples them.
func presentation_snapshot() -> Dictionary:
	var duration := float(_action.get(_action_phase, 0)) * Defs.FRAME
	var snapshot := {
		"state": state, "card_id": String(_action.get("id", "")),
		"action_seq": _action_seq, "phase": _action_phase,
		"phase_progress": clampf(_phase_time / duration, 0.0, 1.0) if duration > 0.0 else 1.0,
		"phase_time": _phase_time, "state_time": state_time,
		"stun_duration": _stun_duration, "local_hitstop": maxf(0.0, _hitstop),
		"facing": facing, "walk_phase": fposmod(_walk_time * WALK_SPEED / WALK_STRIDE, 1.0),
		"walk_blend": _presentation_walk_blend, "moving": _presentation_moving,
		"walk_direction": _presentation_walk_direction,
		"guarding": _guard_hold > 0.0, "dodging": is_invulnerable(),
		"is_super": _is_super, "hp": hp,
	}
	return snapshot


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
	_action_seq += 1
	_terminal_snapshot.clear()
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
	return true


## 回合制合战专用：只把招式动画放出来，不做任何实时结算。
## play_card() 那条链（扣气 / 连招 / 前摇命中判定 / 位移）一步都不走，
## 伤害由 arena 在比牌后统一调 apply_hit()，避免双重结算。
func perform_visual(id: String) -> void:
	var card: Dictionary = Defs.card(id)
	if card.is_empty():
		return
	_visual_only = true
	_combo_bonus = 0
	_combo_name = ""
	_combo_extra = ""
	_is_super = false
	_guard_hold = 0.0
	_sidestep_time = 0.0
	_clear_slide()
	_action = card.duplicate()
	_action["id"] = id
	_action_seq += 1
	_terminal_snapshot.clear()
	_action_phase = "windup"
	_phase_time = 0.0
	_has_hit = false
	state = State.ACTION
	state_time = 0.0
	card_played.emit(id, is_player)


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

	state_time += delta
	_presentation_moving = false

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
				var before := position.x
				position.x = clampf(
					position.x + _moving * WALK_SPEED * delta, ARENA_MIN, ARENA_MAX
				)
				# 相位按**真的走了多远**推进，不按时间。贴住擂台边时身体一步没动，
				# 按时间推进的话步态照转，脚就在原地滑了。
				_walk_time += absf(position.x - before) / WALK_SPEED
				_presentation_moving = absf(position.x - before) > 0.0001
				if _presentation_moving:
					_presentation_walk_direction = 1 if (position.x - before) * float(facing) > 0.0 else -1
			if state == State.DODGE and state_time > 0.25:
				state = State.IDLE

	var walking := _moving != 0.0 and (state == State.IDLE or state == State.DODGE)
	_presentation_walk_blend = move_toward(_presentation_walk_blend, 1.0 if _presentation_moving else 0.0, WALK_BLEND_RATE * delta)
	_walk_blend = move_toward(_walk_blend, 1.0 if walking else 0.0, WALK_BLEND_RATE * delta)
	# 完全停下之后把相位归零，这样每次起步都从同一只脚开始。
	if _walk_blend == 0.0:
		_walk_time = 0.0

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
			_advance_slide()
			# 结算放在 active 的**最后**一 tick。12 张牌的极值都摆在那一帧（表里
			# 最后一个 active 帧就是命中帧），判定因此落在拳完全伸出去的那一刻。
			# 原来每个 active tick 都会调，于是命中发生在**第一个** active tick ——
			# 拳只伸了一半，而 hitstop 又把画面冻在那一帧，玩家看到的是
			# 「拳头还没到，人已经飞了」。
			if _phase_time >= active or active <= 0.0:
				_resolve_active_hit()
				if _action_phase == "active":
					_phase_time = 0.0
					_action_phase = "recover"
		"recover":
			_advance_slide()
			if _phase_time >= recover:
				_end_action()


func _on_active_start() -> void:
	if _visual_only:
		return
	var card := _action
	var id := String(card.get("id", ""))
	var kind := String(card.get("kind", ""))

	# 位移牌必须真的挪人。只画个冲的姿势而位置不变，玩家会以为牌坏了 ——
	# 而且突进原本是用来解决「够不着」的，不挪就等于没有这张牌。
	# 位移不再一帧瞬移。rush 原本一帧挪 172 px（10320 px/s），画面上是整个人被
	# 剪掉重贴，脚也跟着跳 —— 脚没办法「踩」在一个瞬间挪走的地面上。摊到 5 帧后
	# 是 34 px/帧（约 10 倍步速），冲刺还是冲刺，只是看得见过程。
	if kind == Defs.KIND_MOVE:
		var push := 172.0 if id == "rush" else -152.0
		_begin_slide(push * float(facing), 5)
	elif id == "sidestep":
		_begin_slide(-66.0 * float(facing), 5)


func _begin_slide(total: float, frames: int) -> void:
	_slide_left = total
	_slide_frames = maxi(frames, 1)


## 每帧挪掉剩余距离的 1/n，n 逐帧递减 —— 线性摊开。剩余为 0 时什么都不做。
func _advance_slide() -> void:
	if _slide_frames <= 0:
		return
	var step := _slide_left / float(_slide_frames)
	_slide_frames -= 1
	_slide_left -= step
	position.x = clampf(position.x + step, ARENA_MIN, ARENA_MAX)


## 清掉手上没走完的位移。动作被打断（KO、回合结束）时必须调，否则牌已经没了，
## 残余的 _slide_left / _slide_frames 还会在下一个动作里接着把人往前推。
func _clear_slide() -> void:
	_slide_left = 0.0
	_slide_frames = 0


## 气功波从推出去的那双手之间发出，不是从胸口：站架抬高后手在 -150 一带。
## 发波与判定同一个 tick（active 的最后一帧，双手完全推直），
## 否则波会从还没伸出去的拳头上冒出来。
func _fire_projectile() -> void:
	var card := _action
	var origin := position + Vector2(62.0 * facing, -150.0)
	projectile_requested.emit(
		origin, int(card.get("damage", 0)) + _combo_bonus, facing, display_name
	)


func _resolve_active_hit() -> void:
	if _visual_only:
		return
	var card := _action
	if String(card.get("kind", "")) != Defs.KIND_ATTACK:
		return
	if bool(card.get("bullet", false)):
		_fire_projectile()
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
		# 打的是对手，不是自己。apply_hit 里全是「被对手打中」的逻辑
		# （格挡判定读的是防守方的 is_guarding()、闪避读防守方的无敌帧、
		# 信号里 `not is_player` 假设自己是挨打的那一方），所以必须交给 opponent。
		# 气功波那条路径（arena.gd）一直是 target.apply_hit(...)，这里原来是笔误。
		opponent.apply_hit(damage, String(card["id"]), _combo_extra, _is_super)


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
	_visual_only = false
	_clear_slide()
	state = State.IDLE
	state_time = 0.0


## 让 arena 在回合结束时停手。
func freeze() -> void:
	_terminal_snapshot = presentation_snapshot()
	_action = {}
	_action_phase = ""
	_visual_only = false
	_clear_slide()
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

# Kept as a diagnostic status field for the native rendering probes.
var draw_3d_override := true


func _draw() -> void:
	_draw_shadow(visual_shift)


func _draw_shadow(shift: Vector2 = Vector2.ZERO) -> void:
	var spread := 46.0 + 8.0 * absf(_stun_tilt)
	draw_set_transform(shift + Vector2(0, 2), 0.0, Vector2(1.0, 0.32))
	draw_circle(Vector2.ZERO, spread, Color(0, 0, 0, 0.35))
	draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)
