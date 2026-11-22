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
## 招式关节表。走 preload 而不是 global class：非编辑器启动时用的是
## .godot/global_script_class_cache.cfg，新加的 class_name 在缓存刷新前取不到。
const Motion = preload("res://scripts/card_motion.gd")

## 外观层规格（琉音方向 / V4-02 设定图）。走 preload 而不是 class_name：
## 非编辑器启动时新增的 class_name 在 global_script_class_cache 刷新前取不到。
## 名字不能叫 Skin：那是 Godot 内置的骨骼蒙皮类，常量同名会让整棵脚本树
## 报 "shadows a native class" 编译失败。
const SkinSpec = preload("res://scripts/fighter_skin.gd")
## 外观开关。false 就整层回到原自绘剪影 —— 旧绘制一行没删，回退只改这里。
const SKIN_V2 := true

const GROUND_Y := 520.0
const ARENA_MIN := 150.0
const ARENA_MAX := 1130.0
const WALK_SPEED := 215.0
## 走路：一个完整循环（两脚各迈一次）身体前进的距离。这不是美术数，是被腿算出来的。
## 支撑期那只脚的相对位移必须正好等于身体的前进量，而脚的相对位移受腿长限制：
## 骨链只有 92.5 px，髋沉到 64 px 时脚最远只能到 ±65.8 px。站架（前 36 / 后 -44）
## 在髋高 80 px 下后脚已经贴住极限（91.4 px 骨链），所以走起来必须先把髋沉 16 px、
## 后脚收到 -30，脚才有 ±WALK_HALF 的余地。
const WALK_STRIDE := 120.0
## 支撑期占整个循环的比例。0.5 就是「任何时刻总有一只脚在地上」。
const WALK_DUTY := 0.5
## 摆动期脚能抬多高（向上为正，画的时候取负）。
const WALK_LIFT := 9.0
## 走路时髋下沉的高度，以及走起来之后两只脚的基准位置。
const WALK_HIP_DROP := 16.0
const WALK_FRONT := 36.0
const WALK_REAR := -30.0
## 半个循环里脚的相对行程 = WALK_STRIDE * WALK_DUTY / 2。
const WALK_HALF := WALK_STRIDE * WALK_DUTY * 0.5
## 走/停之间过渡的速度（1/秒）。0.11 s 走完，不会一步跳进走路的姿势。
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
## _build_pose 一律不引用，判定语义完全不变。默认 0 时与旧绘制逐像素一致。
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
			if state == State.DODGE and state_time > 0.25:
				state = State.IDLE

	var walking := _moving != 0.0 and (state == State.IDLE or state == State.DODGE)
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


func _draw() -> void:
	var pal := palette()
	var main: Color = pal["main"]
	var dark: Color = pal["dark"]
	var trim: Color = pal["trim"]

	# 影子只跟着平移、不跟着后仰旋转；角色本体用整层 transform 做位移+倾角。
	_draw_shadow(visual_shift)
	draw_set_transform(visual_shift, visual_tilt, Vector2.ONE)

	# 气满时的一圈辉光：让"能放大了"在角色身上直接可见，不用看 UI。
	if meter >= 3.0:
		var glow := Color(trim.r, trim.g, trim.b, 0.06 + 0.05 * sin(_breath * 4.0))
		draw_circle(Vector2(0, -95), 96.0 + 6.0 * sin(_breath * 3.0), glow)

	var p := _build_pose()
	var flash_mix: float = clampf(_flash, 0.0, 1.0)
	# 0.55 上限：再高受击者就整块变白，分不清是谁挨了打。
	var body := main.lerp(Color(1, 1, 1), flash_mix * 0.55)
	var limb := dark.lerp(Color(1, 1, 1), flash_mix * 0.45)

	if SKIN_V2:
		_draw_skin_v2(p, body, trim, flash_mix)
	else:
		# 原自绘剪影，一行未删：SKIN_V2 = false 即可整层回退。
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
	# 复位：Godot 的 draw_set_transform 是「设置」不是「累积」，
	# 不复会把整层偏移留到下一次 _draw / 其它 CanvasItem 指令。
	draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)


func _draw_shadow(shift: Vector2 = Vector2.ZERO) -> void:
	# 影子随受击姿态抖动，落地感来自它而不是角色本身。
	var spread := 46.0 + 8.0 * absf(_stun_tilt)
	draw_set_transform(shift + Vector2(0, 2), 0.0, Vector2(1.0, 0.32))
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


# ─────────────────────────────────────────────────────────────
# appearance-layer V2：琉音方向（V4-02 设定图）
# 只吃 _build_pose() 的 11 关节 + lean，不碰判定、不改动作表。
# 阵营色仍来自 palette()：拳套是唯一随玩家 / 对手变色的部件。
# ─────────────────────────────────────────────────────────────

func _draw_skin_v2(p: Dictionary, body: Color, trim: Color, flash_mix: float) -> void:
	var f := float(facing)
	var white: Color = SkinSpec.WHITE.lerp(Color(1, 1, 1), flash_mix * 0.35)
	var ink: Color = SkinSpec.INK
	var red: Color = SkinSpec.RED
	var gold: Color = SkinSpec.GOLD
	var back_white: Color = white.darkened(0.30)
	var back_ink: Color = ink.lightened(0.10)

	# 后侧肢体先画并压暗，保持与旧绘制一致的前后层次。
	_skin_limb(p["hip"], p["b_knee"], back_white, 20.0, back_ink)
	_skin_limb(p["b_knee"], p["b_foot"], back_white, 17.0, back_ink)
	_skin_shoe(p["b_foot"], back_ink, gold.darkened(0.25), f)
	_skin_limb(p["shoulder"], p["b_elbow"], back_white, 17.0, back_ink)
	_skin_limb(p["b_elbow"], p["b_hand"], back_white, 15.0, back_ink)
	_skin_glove(p["b_hand"], body.darkened(0.35), trim.darkened(0.30), f)

	_skin_torso(p, white, ink, red, gold, f)
	_skin_head(p, ink, red, gold, f)

	_skin_limb(p["hip"], p["f_knee"], white, 22.0, ink)
	_skin_limb(p["f_knee"], p["f_foot"], white, 18.0, ink)
	_skin_shoe(p["f_foot"], ink, gold, f)
	_skin_limb(p["shoulder"], p["f_elbow"], white, 19.0, ink)
	_skin_limb(p["f_elbow"], p["f_hand"], white, 16.0, ink)
	_skin_glove(p["f_hand"], body, trim, f)

	_skin_ring_blade(p, gold, f)


func _skin_limb(a: Vector2, b: Vector2, fill: Color, width: float, outline: Color) -> void:
	draw_line(a, b, outline, width + 5.0, true)
	draw_line(a, b, fill, width, true)
	draw_circle(b, width * 0.5, fill)


func _skin_glove(at: Vector2, fill: Color, edge: Color, f: float) -> void:
	var r: float = SkinSpec.GLOVE_RADIUS
	draw_circle(at, r + 3.0, SkinSpec.INK)
	draw_circle(at, r, fill)
	draw_arc(at, r, 0.0, TAU, 24, SkinSpec.GOLD, 2.0)
	draw_circle(at + Vector2(5.0 * f, -5.0), 4.0, Color(edge.r, edge.g, edge.b, 0.55))


func _skin_shoe(at: Vector2, fill: Color, gold: Color, f: float) -> void:
	var top: float = SkinSpec.SHOE_TOP
	var pts := PackedVector2Array([
		at + Vector2(-15.0, top),
		at + Vector2(15.0 * f, top),
		at + Vector2(20.0 * f, 2.0),
		at + Vector2(-17.0, 2.0),
	])
	draw_colored_polygon(pts, fill)
	draw_line(at + Vector2(-17.0, 1.0), at + Vector2(20.0 * f, 1.0), gold, 2.5, true)
	draw_circle(at + Vector2(6.0 * f, -9.0), 3.2, gold)


func _skin_torso(p: Dictionary, white: Color, ink: Color, red: Color, gold: Color, f: float) -> void:
	var hip: Vector2 = p["hip"]
	var shoulder: Vector2 = p["shoulder"]
	var lean: float = p["lean"]
	var dir := Vector2(lean, 0.0)
	var half: float = SkinSpec.TORSO_HALF

	# 白色外层：从髋到肩的梯形，盖住整个躯干（中性全覆盖）。
	var chest := PackedVector2Array([
		hip + Vector2(-half, 6.0),
		shoulder + Vector2(-half - 3.0, 2.0),
		shoulder + Vector2(half + 1.0, 0.0) + dir,
		hip + Vector2(half, 4.0),
	])
	draw_colored_polygon(chest, white)

	# 黑色内层交领：两肩内侧收成 V，白边压出领口。
	var neck_l := shoulder + Vector2(-12.0, 4.0)
	var neck_r := shoulder + Vector2(12.0, 4.0) + dir
	var v_tip := hip + Vector2(0.0, -26.0)
	var collar := PackedVector2Array([neck_l, neck_r, v_tip])
	draw_colored_polygon(collar, ink)
	draw_line(neck_l, v_tip, white, 4.0, true)
	draw_line(neck_r, v_tip, white, 4.0, true)

	# 红腰带 + 金色 8 字扣 + 腰侧中国结（三道流苏）。
	draw_line(hip + Vector2(-half - 2.0, -4.0), hip + Vector2(half + 2.0, -4.0), red, 9.0, true)
	draw_arc(hip + Vector2(-6.0 * f, -4.0), 5.0, 0.0, TAU, 16, gold, 2.0)
	draw_arc(hip + Vector2(6.0 * f, -4.0), 5.0, 0.0, TAU, 16, gold, 2.0)
	var knot := hip + Vector2(22.0 * f, -2.0)
	var diamond := PackedVector2Array([
		knot + Vector2(0.0, -7.0), knot + Vector2(6.0, 0.0),
		knot + Vector2(0.0, 7.0), knot + Vector2(-6.0, 0.0),
	])
	draw_colored_polygon(diamond, red)
	draw_line(knot + Vector2(-3.0, 7.0), knot + Vector2(-3.0, 17.0), red, 2.0, true)
	draw_line(knot + Vector2(0.0, 7.0), knot + Vector2(0.0, 17.0), red, 2.0, true)
	draw_line(knot + Vector2(3.0, 7.0), knot + Vector2(3.0, 17.0), red, 2.0, true)


func _skin_head(p: Dictionary, ink: Color, red: Color, gold: Color, f: float) -> void:
	var head: Vector2 = p["head"]
	var r := 20.0
	var white: Color = SkinSpec.WHITE

	# 后发压在脸后面；脸是浅肤色，不是阵营色。
	draw_circle(head + Vector2(-4.0 * f, 2.0), r + 4.0, ink)
	draw_circle(head, r, SkinSpec.SKIN_FACE)

	# 刘海只盖额头，一缕白挑染对应「黑白交织」。
	var bangs := PackedVector2Array([
		head + Vector2(-20.0, -6.0), head + Vector2(-17.0, -17.0),
		head + Vector2(0.0, -21.0), head + Vector2(17.0, -15.0),
		head + Vector2(20.0, -6.0),
	])
	draw_colored_polygon(bangs, ink)
	draw_line(head + Vector2(-14.0 * f, -12.0), head + Vector2(-6.0 * f, -18.0), white, 3.5, true)

	# 空心双环发髻（丫鬟），前后错开；内圈用洞色挖空。
	_skin_bun(head + Vector2(-13.0 * f, -26.0), ink, SkinSpec.BUN_RADIUS)
	_skin_bun(head + Vector2(12.0 * f, -28.0), white, SkinSpec.BUN_RADIUS - 1.0)

	# 一黑一白绒球 + 金 / 银发夹。
	draw_circle(head + Vector2(-19.0 * f, -22.0), 4.0, ink)
	draw_circle(head + Vector2(18.0 * f, -24.0), 4.0, white)
	draw_line(head + Vector2(4.0 * f, -12.0), head + Vector2(12.0 * f, -13.0), gold, 2.5, true)
	draw_line(head + Vector2(-2.0 * f, -11.0), head + Vector2(-9.0 * f, -12.0), SkinSpec.SILVER, 2.5, true)

	# 俏皮半睁眼：细眼线 + 小瞳孔 + 一点 smirk，不画圆高光。
	var eye := head + Vector2(9.0 * f, -3.0)
	draw_line(eye + Vector2(-6.0, 0.0), eye + Vector2(6.0, 0.0), ink, 2.2, true)
	draw_circle(eye + Vector2(2.0 * f, 1.0), 2.2, ink)
	draw_line(head + Vector2(6.0 * f, 9.0), head + Vector2(13.0 * f, 8.0), red.darkened(0.45), 1.6, true)


func _skin_bun(at: Vector2, fill: Color, radius: float) -> void:
	draw_circle(at, radius, fill)
	draw_circle(at, radius * 0.45, SkinSpec.HOLE)
	draw_arc(at, radius, 0.0, TAU, 18, fill.darkened(0.35), 1.5)


func _skin_ring_blade(p: Dictionary, gold: Color, f: float) -> void:
	# 腰侧挂件：一黑一白两道弧，暗示可一分为二的环刃。
	var hip: Vector2 = p["hip"]
	var at := hip + Vector2(-26.0 * f, -10.0)
	draw_arc(at, 11.0, -1.2, 1.9, 16, gold, 3.0)
	draw_arc(at + Vector2(3.0 * f, 2.0), 11.0, 1.9, 4.2, 14, SkinSpec.WHITE, 2.5)


## 一个步态循环里相位 p（0..1）处的脚：x = 沿面向轴的相对位移（向前为正），
## y = 抬脚高度（向上为负，与绘制坐标一致）。
## 支撑期 [0, WALK_DUTY) 里 x **线性后退** —— 后退速度正好等于身体的前进速度，
## 世界坐标因此不动，脚是踩住的；摆动期用 smoothstep 加速再减速，落地不带速度。
func _gait(p: float) -> Vector2:
	if p < WALK_DUTY:
		return Vector2(WALK_HALF * (1.0 - 2.0 * p / WALK_DUTY), 0.0)
	var q := (p - WALK_DUTY) / (1.0 - WALK_DUTY)
	var e := q * q * (3.0 - 2.0 * q)
	return Vector2(WALK_HALF * (2.0 * e - 1.0), -WALK_LIFT * sin(PI * q))


## 走路的膝盖：落在髋-脚连线的中点，再往面向方向顶出去一点 —— 膝盖不弯就不是
## 走，是滑步。腿长只有 92.5 px，弯下来才腾得出步子。
func _gait_knee(hip: Vector2, foot: Vector2) -> Vector2:
	var mid := (hip + foot) * 0.5
	return Vector2(mid.x + 10.0 * float(facing), mid.y - 5.0)


func _build_pose() -> Dictionary:
	var f := float(facing)
	var breathe := sin(_breath * 2.4) * 3.0
	var w := _walk_blend
	# 步态相位：按走过的距离算，不按时间算 —— 脚能不能踩实取决于身体挪了多少。
	var gp := fposmod(_walk_time * WALK_SPEED / WALK_STRIDE, 1.0)
	# 走路时身体压低 16 px（腿才够得着），支撑中段再顶起来一点（一个循环两次）。
	var bob := (WALK_HIP_DROP - 3.0 * absf(sin(PI * gp))) * w
	# 站架：屈膝、后脚在后、后手护脸。数值必须与 data/card_motion.json 的
	# `stance` 一致 —— 那是每一招起手/收招归位的那一帧，对不上就会每招跳一下。
	# 两个数不是手写的美术意图而是 Blender 解算的读回值：后肘由骨长决定；后手从
	# (-6,-146) 挪到 (-24,-152) 是因为原来那只拳头距肩只有 4.5 px，等于长在三角
	# 肌里（看不见，且躯干一前倾后臂就会被缩短）。抬到下巴后面之后，后手是一只能
	# 认出来的护手，剪影才读得成「双手护头」。
	var hip := Vector2(0, -80 + breathe + bob)
	var shoulder := Vector2(2.0 * f, -148 + breathe + bob)
	var head := Vector2(4.0 * f, -172 + breathe + bob)
	var lean := 0.0

	# 站姿默认关节
	var f_elbow := Vector2(30.0 * f, -132.0 + breathe)
	var f_hand := Vector2(44.0 * f, -156.0 + breathe)
	var b_elbow := Vector2(-18.0 * f, -130.0 + breathe)
	var b_hand := Vector2(-24.0 * f, -152.0 + breathe)
	var f_knee := Vector2(34.0 * f, -40.0)
	var f_foot := Vector2(36.0 * f, 0.0)
	var b_knee := Vector2(-24.2 * f, -42.1)
	var b_foot := Vector2(-44.0 * f, 0.0)

	# 走路：脚要真的踩在地上。
	# 世界坐标 = position.x + 相对偏移，而 position.x 每帧匀速前进，所以支撑期
	# 那只脚的相对偏移必须以**同样的速度**往后流。原来用 sin(_walk_time*9) 摆腿，
	# 正弦的速度和身体的匀速毫无关系 —— 两脚全程在冰上滑（实测踩实帧 22%）。
	# 这里把一步拆成支撑/摆动两段：支撑期线性后退，摆动期 smoothstep 甩回来。
	if w > 0.0:
		var dir := 1.0 if _moving * f > 0.0 else -1.0  # 倒着走时脚的运动是反的
		var gf := _gait(fposmod(gp + 0.5, 1.0))        # 前脚比后脚晚半个循环
		var gb := _gait(gp)
		var ff_w := Vector2((WALK_FRONT + dir * gf.x) * f, gf.y)
		var bf_w := Vector2((WALK_REAR + dir * gb.x) * f, gb.y)
		f_foot = f_foot.lerp(ff_w, w)
		b_foot = b_foot.lerp(bf_w, w)
		f_knee = f_knee.lerp(_gait_knee(hip, ff_w), w)
		b_knee = b_knee.lerp(_gait_knee(hip, bf_w), w)
		# 手臂与前脚反向摆，幅度很小 —— 手还得护着脸。
		var sw := dir * gf.x / WALK_HALF
		f_hand += Vector2(-7.0 * sw * f, 3.0 * absf(sw)) * w
		b_hand += Vector2(8.0 * sw * f, 3.0 * absf(sw)) * w

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
			# 位移由 position.x 负责（见 _on_active_start），姿势层不再自己再挪一次。
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

		# 烘焙表优先：上面那一段是兜底。12 套招式在 Blender 里按游戏自己的帧数
		# 逐帧烘过（split 与 windup/active/recover 逐卡核对一致），表里的关节是
		# 绝对坐标，所以整副覆盖即可，不需要插值 —— 帧索引就是结算时刻。
		# 表以「无呼吸的站姿」为基准，补回同样的呼吸/走动位移，否则进招那一帧会跳 3px。
		var baked := Motion.sample(id, phase, progress, f)
		if not baked.is_empty():
			var core := Vector2(0.0, breathe + bob)
			var arm := Vector2(0.0, breathe)
			hip = baked["hip"] + core
			shoulder = baked["shoulder"] + core
			head = baked["head"] + core
			f_elbow = baked["f_elbow"] + arm
			f_hand = baked["f_hand"] + arm
			b_elbow = baked["b_elbow"] + arm
			b_hand = baked["b_hand"] + arm
			f_knee = baked["f_knee"]
			f_foot = baked["f_foot"]
			b_knee = baked["b_knee"]
			b_foot = baked["b_foot"]
			lean = float(baked["lean"])

	# 受击反应走表：后仰、回弹、后脚拖行都在里面，按硬直进度归一化播放，
	# 最后一帧正好是站架，所以恢复控制权时不会跳。KO 不接（它有自己的倒地曲线）。
	if state == State.HITSTUN or state == State.BLOCKSTUN:
		var react_name := "hit_light"
		if state == State.BLOCKSTUN:
			react_name = "block"
		elif absf(_stun_tilt) >= 0.6:
			react_name = "hit_heavy"
		var t01 := clampf(state_time / maxf(_stun_duration, 0.01), 0.0, 1.0)
		var react := Motion.sample_react(react_name, t01, f)
		if not react.is_empty():
			hip = react["hip"] + Vector2(0.0, breathe)
			shoulder = react["shoulder"] + Vector2(0.0, breathe)
			head = react["head"] + Vector2(0.0, breathe)
			f_elbow = react["f_elbow"] + Vector2(0.0, breathe)
			f_hand = react["f_hand"] + Vector2(0.0, breathe)
			b_elbow = react["b_elbow"] + Vector2(0.0, breathe)
			b_hand = react["b_hand"] + Vector2(0.0, breathe)
			f_knee = react["f_knee"]
			f_foot = react["f_foot"]
			b_knee = react["b_knee"]
			b_foot = react["b_foot"]
			lean = float(react["lean"])

	# 侧闪的整体平移曾经在这里再叠一层：`position.x` 已经挪了 66 px，这里又给上身
	# 7 个关节加 66 px（双脚不动），于是上身画面上走了 132 px、判定只走了 66 px ——
	# 视觉在骗玩家，而且 66 px 全由腿吸收，前腿被拉到 1.49 倍（橡皮腿）。
	# 表里已经烘了侧闪的身体位移，这层不再需要。

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
