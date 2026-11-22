extends Node2D
## 牌拳 / CARD BOXER —— 主控制器。
##
## 一场对局：三局两胜，双方各有 5 张手牌。
## 玩法骨架由 BATTLE_MODE 决定：
##   "taikou"（默认）= 太阁 IV 合战，回合制同时亮 3 张比牌型；
##   "realtime"      = 原实时格斗，出牌即出招，按牌序结算连招与大招。
##
## 这里承担四件事：回合流程、手牌经济、命中后的表现（震屏/火花/停帧）、
## 以及背景的整套绘制。角色自己画自己（fighter.gd），界面自己画自己（hud.gd）。

const Defs = preload("res://scripts/card_data.gd")
const FighterScript = preload("res://scripts/fighter.gd")
const AIScript = preload("res://scripts/ai_controller.gd")
const HUDScript = preload("res://scripts/hud.gd")
const FxLayerScript = preload("res://scripts/fx_layer.gd")
const BackdropTexture = preload("res://background/arena.png")
const Rules = preload("res://scripts/taikou_rules.gd")
const TaikouAI = preload("res://scripts/taikou_ai.gd")
const Rage = preload("res://scripts/taikou_rage.gd")

## 玩法骨架："taikou" = 太阁 IV 回合制比牌（默认）；"realtime" = 原实时格斗兜底。
## 改成 realtime 即可完整回到改造前的玩法，不需要回滚任何代码。
const BATTLE_MODE := "taikou"
const TK_PLAY := 3
const TK_DISCARD_MAX := 3
## 一局合战打满这么多回亮牌就按剩余兵力收局；HUD 与结算文案都读本常量，别在别处写死回数。
const TK_MAX_TURNS := 3

const HAND_SIZE := 5
const COOLDOWN_TOTAL := 2.0
const ROUND_SECONDS := 60.0
const GROUND_Y := 520.0
#: 与 fighter.gd 的边界保持一致：牌把人推到哪里，两个文件都得同意。
const ARENA_MIN := 150.0
const ARENA_MAX := 1130.0

## 手牌攻击牌不足时从这里补，保持牌面多样而不是一水儿的刺拳。
const ATTACK_POOL := ["jab", "jab", "cross", "uppercut", "sweep", "throw"]

var world: Node2D
var fx_layer: Node2D
var player
var enemy
var ai
var hud

var hand: Array = []
var cooldowns: Array = []
var enemy_hand: Array = []
var enemy_cooldowns: Array = []
var cooldown_total := COOLDOWN_TOTAL

var round_wins := [0, 0]
var round_index := 1
var round_time_left := ROUND_SECONDS
var round_phase := "intro"  # intro / fight / over / match_over
var phase_time := 0.0
var paused := false
var selected_index := -1

var banner_text := ""
var banner_sub := ""
var banner_color := Color(1, 1, 1)
var banner_time := 0.0

var combo_count := 0
var combo_shown := 0.0
var effects: Array = []
var projectiles: Array = []

var _deck: Array = []
var _enemy_deck: Array = []
var _shake := 0.0
var _flash := 0.0
var _combo_timer := 0.0
var _global_hitstop := 0.0
var _intro_label := ""
var _slowmo := 0.0
var _time := 0.0
var _log_timer := 0.0
var _background_cache: Dictionary = {}

# 开发用截图钩子：设了环境变量才生效，不介入玩法。
var _capture_dir := ""
var _capture_times: Array = []
var _capture_index := 0
#: 在第一次真实命中时抓一张。命中只持续零点几秒，靠时间点碰运气抓不到。
var _capture_on_hit := false
var _hit_shot_taken := false

# 演示模式：把玩家侧也交给 AI，用于自动跑完整局（只看流程，不算玩法）。
var demo_ai = null

## 太阁 IV 合战（回合制）状态。
var battle_mode: String = BATTLE_MODE
var tk_phase := "discard"        # discard / select / reveal / resolve
var tk_turn := 1
var tk_phase_time := 0.0
var tk_marks: Array = []          # 当前阶段勾选的手牌下标
var tk_player_reveal: Array = []  # 亮出的 3 个 rank
var tk_enemy_reveal: Array = []
var tk_player_ids: Array = []     # 亮出的牌 id，只用于播动画
var tk_enemy_ids: Array = []
var tk_player_result: Dictionary = {}
var tk_enemy_result: Dictionary = {}
var tk_winner := ""
var tk_damage := 0
var tk_bot := false               # CARD_BOXER_TAIKOU_BOT：无输入自动对战，仅供验收

## 怒火槽：挨打攒怒，满槽时本回亮出的 3 张牌升 EX（见 taikou_rage.gd）。
## 跨「局」保留、只在 _start_match() 清零——三回制一局太短，每局清零就几乎用不上。
var tk_player_rage := 0.0
var tk_enemy_rage := 0.0
var tk_player_ex := false          # 本回是否消耗怒火触发了 EX
var tk_enemy_ex := false
var tk_player_ex_boosted := false # 升级是否真被采用（保底时 false）
var tk_enemy_ex_boosted := false


func _ready() -> void:
	world = Node2D.new()
	world.name = "World"
	add_child(world)

	player = FighterScript.new()
	player.is_player = true
	player.display_name = "你"
	world.add_child(player)
	player.position = Vector2(430, GROUND_Y)

	enemy = FighterScript.new()
	enemy.is_player = false
	enemy.display_name = "青岚"
	world.add_child(enemy)
	enemy.position = Vector2(850, GROUND_Y)

	player.opponent = enemy
	enemy.opponent = player

	player.projectile_requested.connect(_on_projectile_requested)
	player.hit_confirmed.connect(_on_hit_confirmed)
	player.super_confirmed.connect(_on_super_confirmed)
	player.card_played.connect(_on_card_played)
	enemy.projectile_requested.connect(_on_projectile_requested)
	enemy.hit_confirmed.connect(_on_hit_confirmed)
	enemy.super_confirmed.connect(_on_super_confirmed)
	enemy.card_played.connect(_on_card_played)

	ai = AIScript.new(enemy, 2)

	# 顺序即层序：world（角色）→ fx（火花/数字）→ hud（界面）。
	fx_layer = FxLayerScript.new()
	fx_layer.arena = self
	add_child(fx_layer)

	hud = HUDScript.new()
	hud.arena = self
	hud.size = Vector2(1280, 720)
	add_child(hud)

	_build_backdrop()
	_capture_dir = OS.get_environment("CARD_BOXER_CAPTURE")
	_capture_on_hit = OS.get_environment("CARD_BOXER_CAPTURE_HIT") != ""
	var at := OS.get_environment("CARD_BOXER_CAPTURE_AT")
	if at == "":
		_capture_times = [4.6]
	else:
		for part in at.split(","):
			_capture_times.append(float(part))
		_capture_times.sort()
	if OS.get_environment("CARD_BOXER_BOT") != "":
		demo_ai = AIScript.new(player, 3)
	tk_bot = OS.get_environment("CARD_BOXER_TAIKOU_BOT") != ""
	_start_match()
	# 验收钩子：只在设了环境变量时把双方怒火直接灌满，用来截 EX 亮牌帧。
	var rage_start := OS.get_environment("CARD_BOXER_RAGE_START")
	if rage_start != "":
		tk_player_rage = clampf(float(rage_start), 0.0, Rage.MAX)
		tk_enemy_rage = tk_player_rage


# ── 对局流程 ────────────────────────────────────────────────

func _start_match() -> void:
	round_wins = [0, 0]
	round_index = 1
	tk_player_rage = 0.0
	tk_enemy_rage = 0.0
	_deck = _shuffled_deck()
	_enemy_deck = _shuffled_deck()
	_start_round()


func _start_round() -> void:
	player.reset_for_round(430, 1)
	enemy.reset_for_round(850, -1)
	_clear_round_effects()
	round_time_left = ROUND_SECONDS
	round_phase = "intro"
	phase_time = 0.0
	_intro_label = ""
	_fill_hand(hand, cooldowns, _deck, false)
	_fill_hand(enemy_hand, enemy_cooldowns, _enemy_deck, true)
	if battle_mode == "taikou":
		_reset_taikou_turn(true)
	else:
		_banner("第 %d 回合" % round_index, "1-5 出牌 · A/D 移动", Color(0.96, 0.90, 0.74), 1.0)


func _fill_hand(target_hand: Array, target_cd: Array, deck: Array, is_ai: bool) -> void:
	target_hand.clear()
	target_cd.clear()
	for i in range(HAND_SIZE):
		target_hand.append(_draw_from(deck))
		target_cd.append(0.0)
	_ensure_opener(target_hand)
	if is_ai:
		return


## 手牌必须至少有一张 0 费的进攻牌。
##
## 没有它，这一回合就只能出位移和守御，气不会涨，永远打不出第一下 ——
## 自动对战跑出来时双方血量整局停在 100，就是缺这条保证。
func _ensure_opener(target_hand: Array) -> void:
	for id: Variant in target_hand:
		if id == null:
			continue
		var card := Defs.card(String(id))
		if String(card.get("kind", "")) == Defs.KIND_ATTACK and int(card.get("cost", 0)) == 0:
			return
	if target_hand.is_empty():
		return
	target_hand[randi_range(0, target_hand.size() - 1)] = "jab"


func _draw_from(deck: Array) -> String:
	if deck.is_empty():
		var refill := _shuffled_deck()
		for card_id in refill:
			deck.append(card_id)
	var idx := randi_range(0, deck.size() - 1)
	return String(deck.pop_at(idx))


## 补一张牌，并且保证手牌里始终有至少两张进攻牌。
##
## 只保证一张不够：出掉它之后整手就剩位移和守御，气涨到满也打不出去。
## 自动对战里出现过「气 5.0 / 手牌只有侧闪和突进 / 双方贴脸站着」的场面。
func _draw_for_slot(target_hand: Array, deck: Array, slot: int) -> String:
	var attacks := 0
	for i in range(target_hand.size()):
		if i == slot:
			continue
		var id: Variant = target_hand[i]
		if id == null:
			continue
		if String(Defs.card(String(id)).get("kind", "")) == Defs.KIND_ATTACK:
			attacks += 1
	if attacks >= 2:
		return _draw_from(deck)
	if attacks == 0 or randf() < 0.55:
		return String(ATTACK_POOL[randi_range(0, ATTACK_POOL.size() - 1)])
	return _draw_from(deck)


## 两个人不能站在同一个格子里。贴到 78 像素以内就互相顶开一点，
## 顺带让「贴身」变成一个有成本的位置，而不是可以无限叠加的状态。
func _push_apart() -> void:
	var dx: float = enemy.position.x - player.position.x
	var gap: float = absf(dx)
	# 100 像素起步：再近两条手臂就穿模了。这个距离仍短于所有近身牌的射程，
	# 所以「贴身」照样打得着，只是不许两个人站在同一个格子里。
	if gap >= 100.0 or gap < 0.01:
		return
	var dir: float = 1.0 if dx > 0.0 else -1.0
	var push: float = (100.0 - gap) * 0.8
	player.position.x = clampf(player.position.x - push * dir, ARENA_MIN, ARENA_MAX)
	enemy.position.x = clampf(enemy.position.x + push * dir, ARENA_MIN, ARENA_MAX)


func _shuffled_deck() -> Array:
	var copy: Array = Defs.DECK.duplicate()
	for i in range(copy.size() - 1, 0, -1):
		var j := randi_range(0, i)
		var tmp: Variant = copy[i]
		copy[i] = copy[j]
		copy[j] = tmp
	return copy


func _clear_round_effects() -> void:
	effects.clear()
	projectiles.clear()
	combo_count = 0
	combo_shown = 0.0
	_combo_timer = 0.0
	_shake = 0.0
	_flash = 0.0


func _end_round(winner: String, reason: String) -> void:
	if round_phase != "fight":
		return
	round_phase = "over"
	phase_time = 0.0
	player.freeze()
	enemy.freeze()
	if winner == "player":
		round_wins[0] += 1
		_banner(reason, "这一回合归你", Color(0.99, 0.76, 0.36), 1.2)
	elif winner == "enemy":
		round_wins[1] += 1
		_banner(reason, "青岚拿下这一回合", Color(0.42, 0.80, 0.98), 1.2)
	else:
		_banner(reason, "双方都没能拿下", Color(0.86, 0.88, 0.95), 1.2)
	_flash = 0.55
	_shake = 9.0


func _advance_after_round() -> void:
	if round_wins[0] >= 2 or round_wins[1] >= 2:
		round_phase = "match_over"
		phase_time = 0.0
		if round_wins[0] > round_wins[1]:
			_banner("你赢了", "按 R 再来一场", Color(0.99, 0.78, 0.36), 999.0)
		else:
			_banner("你输了", "按 R 再来一场", Color(0.44, 0.80, 0.98), 999.0)
		_flash = 0.5
	else:
		round_index += 1
		_start_round()


# ── 每帧 ────────────────────────────────────────────────────

func _process(delta: float) -> void:
	_time += delta
	if paused:
		queue_redraw()
		return

	if _global_hitstop > 0.0:
		_global_hitstop -= delta
		_tick_effects(delta * 0.25)
		world.position = _shake_offset()
		fx_layer.position = world.position
		fx_layer.queue_redraw()
		queue_redraw()
		return

	var dt := delta
	if _slowmo > 0.0:
		_slowmo -= delta
		dt = delta * 0.35

	phase_time += dt
	_shake = move_toward(_shake, 0.0, dt * 70.0)
	_flash = move_toward(_flash, 0.0, dt * 3.2)
	banner_time = maxf(0.0, banner_time - dt)
	if combo_shown > 0.0:
		combo_shown = maxf(0.0, combo_shown - dt)
		_combo_timer -= dt
		if _combo_timer <= 0.0:
			combo_count = 0

	match round_phase:
		"intro":
			_tick_intro(dt)
		"fight":
			_tick_fight(dt)
		"over":
			if phase_time > 2.4:
				_advance_after_round()
		"match_over":
			player.tick(dt, 0.0, false)
			enemy.tick(dt, 0.0, false)

	_tick_projectiles(dt)
	_tick_effects(dt)
	world.position = _shake_offset()
	fx_layer.position = world.position
	fx_layer.queue_redraw()
	queue_redraw()
	_maybe_capture()


func _capture_hit_shot() -> void:
	if _capture_dir == "":
		return
	await RenderingServer.frame_post_draw
	var image := get_viewport().get_texture().get_image()
	image.save_png("%s/shot_hit.png" % _capture_dir)


func _maybe_capture() -> void:
	if _capture_dir == "" or _capture_index >= _capture_times.size():
		return
	if _time < float(_capture_times[_capture_index]):
		return
	var path := "%s/shot_%02d.png" % [_capture_dir, _capture_index + 1]
	_capture_index += 1
	await RenderingServer.frame_post_draw
	var image := get_viewport().get_texture().get_image()
	image.save_png(path)
	if _capture_index >= _capture_times.size():
		get_tree().quit()


func _tick_intro(dt: float) -> void:
	var step: int = int(phase_time / 0.85)
	var labels := ["第 %d 回合" % round_index, "3", "2", "1", "开打！"]
	if step < labels.size() and labels[step] != _intro_label:
		_intro_label = labels[step]
		var color := Color(0.96, 0.90, 0.74)
		if step == labels.size() - 1:
			color = Color(1.0, 0.66, 0.28)
		var intro_hint := "1-5 选牌 · 空格确认" if battle_mode == "taikou" else "1-5 出牌 · A/D 移动"
		_banner(_intro_label, "" if step > 0 else intro_hint, color, 0.8)
	player.tick(dt, 0.0, false)
	enemy.tick(dt, 0.0, false)
	if phase_time > 0.85 * 4.0 + 0.35:
		round_phase = "fight"
		phase_time = 0.0


func _tick_fight(dt: float) -> void:
	if battle_mode == "taikou":
		_tick_taikou(dt)
		return
	round_time_left = maxf(0.0, round_time_left - dt)

	# 气会自己慢慢涨：出牌经济不该被一次坏抽牌锁死。
	player.add_meter(0.18 * dt)
	enemy.add_meter(0.18 * dt)

	if demo_ai != null:
		_log_timer += dt
		if _log_timer >= 4.0:
			_log_timer = 0.0
			print("[BOT] t=%.1f hp=%d/%d meter=%.1f/%.1f hand=%s enemy=%s" % [
				_time, player.hp, enemy.hp, player.meter, enemy.meter,
				str(hand), str(enemy_hand)
			])

	if demo_ai != null:
		var auto: Dictionary = demo_ai.update(dt, enemy, hand)
		if int(auto["play"]) >= 0:
			_try_play(int(auto["play"]))
		player.tick(dt, float(auto["move"]), true)
	else:
		var move := 0.0
		if Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT):
			move -= 1.0
		if Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT):
			move += 1.0
		player.tick(dt, move, true)

	var decision: Dictionary = ai.update(dt, player, enemy_hand)
	if int(decision["play"]) >= 0:
		_try_enemy_play(int(decision["play"]))
	enemy.tick(dt, float(decision["move"]), true)

	player.face_toward(enemy.position.x)
	enemy.face_toward(player.position.x)

	# 手牌冷却
	for i in range(hand.size()):
		if hand[i] == null:
			cooldowns[i] = maxf(0.0, float(cooldowns[i]) - dt)
			if cooldowns[i] <= 0.0:
				hand[i] = _draw_for_slot(hand, _deck, i)
	for i in range(enemy_hand.size()):
		if enemy_hand[i] == null:
			enemy_cooldowns[i] = maxf(0.0, float(enemy_cooldowns[i]) - dt)
			if enemy_cooldowns[i] <= 0.0:
				enemy_hand[i] = _draw_for_slot(enemy_hand, _enemy_deck, i)

	_push_apart()

	if player.hp <= 0 or enemy.hp <= 0:
		var winner := "player"
		if enemy.hp <= 0 and player.hp <= 0:
			winner = "player" if player.hp >= enemy.hp else "enemy"
		elif enemy.hp <= 0:
			winner = "player"
		else:
			winner = "enemy"
		_end_round(winner, "K.O.")
	elif round_time_left <= 0.0:
		if player.hp > enemy.hp:
			_end_round("player", "时间到")
		elif enemy.hp > player.hp:
			_end_round("enemy", "时间到")
		else:
			_end_round("draw", "时间到")



# ── 太阁 IV 合战：回合制比牌 ─────────────────────────────────
#
# 一轮 = 弃牌换牌 → 选 3 张 → 双方同时亮牌 → 比牌型 → 赢家结算伤害 → 补牌。
# 实时格斗那套（前摇 / 距离 / 气 / 读牌 AI）在这条分支里一步都不跑，
# 角色只借 perform_visual() 播动画，伤害统一由 apply_hit() 结算。
# 把 BATTLE_MODE 改回 "realtime" 就完整回到原玩法，不需要回滚代码。

func _reset_taikou_turn(new_round: bool) -> void:
	if new_round:
		tk_turn = 1
	tk_phase = "discard"
	tk_phase_time = 0.0
	tk_marks.clear()
	tk_player_reveal.clear()
	tk_enemy_reveal.clear()
	tk_player_ids.clear()
	tk_enemy_ids.clear()
	tk_player_result = {}
	tk_enemy_result = {}
	tk_winner = ""
	tk_damage = 0
	tk_player_ex = false
	tk_enemy_ex = false
	tk_player_ex_boosted = false
	tk_enemy_ex_boosted = false
	_banner(
		"第 %d 轮 · 弃牌" % tk_turn,
		"1-5 标记要换掉的牌（可 0 张） · 空格确认",
		Color(0.96, 0.90, 0.74), 0.9
	)


func _tick_taikou(dt: float) -> void:
	tk_phase_time += dt
	# 动画照常驱动；回合制不允许移动，也不跑实时 AI / 实时出牌 / 冷却补牌。
	player.tick(dt, 0.0, false)
	enemy.tick(dt, 0.0, false)
	player.face_toward(enemy.position.x)
	enemy.face_toward(player.position.x)

	# 无输入自动对战：只用于验收与截帧，不介入玩法决策。
	if tk_bot and (tk_phase == "discard" or tk_phase == "select") and tk_phase_time > 0.8:
		_taikou_confirm()

	match tk_phase:
		"reveal":
			if tk_phase_time >= 1.5:
				_resolve_taikou()
		"resolve":
			if tk_phase_time >= 1.9:
				_finish_taikou_turn()

	if player.hp <= 0 or enemy.hp <= 0:
		_end_taikou_round()


func _taikou_toggle(index: int) -> void:
	if round_phase != "fight" or index < 0 or index >= hand.size():
		return
	if hand[index] == null:
		return
	if tk_marks.has(index):
		tk_marks.erase(index)
		return
	var limit := TK_DISCARD_MAX if tk_phase == "discard" else TK_PLAY
	if tk_marks.size() >= limit:
		_push_float_text(
			player.position + Vector2(0, -210),
			"最多 %d 张" % limit, Color(0.85, 0.42, 0.42)
		)
		return
	tk_marks.append(index)


func _taikou_confirm() -> void:
	if round_phase != "fight":
		return
	match tk_phase:
		"discard":
			_do_taikou_discard()
		"select":
			if not tk_bot and tk_marks.size() != TK_PLAY:
				_push_float_text(
					player.position + Vector2(0, -210),
					"请选满 3 张", Color(0.85, 0.42, 0.42)
				)
				return
			_do_taikou_reveal()


func _do_taikou_discard() -> void:
	# 弃牌 = 把该槽位换成一张新牌，等价于太阁 IV 的「每轮弃最多 3 张再补」。
	var mine: Array = TaikouAI.choose_discards(hand) if tk_bot else tk_marks.duplicate()
	for i in mine:
		hand[i] = _draw_from(_deck)
	var theirs: Array = TaikouAI.choose_discards(enemy_hand)
	for i in theirs:
		enemy_hand[i] = _draw_from(_enemy_deck)
	tk_marks.clear()
	tk_phase = "select"
	tk_phase_time = 0.0
	_banner(
		"第 %d 轮 · 选牌" % tk_turn,
		"1-5 选 3 张凑牌型 · 空格亮牌",
		Color(0.96, 0.90, 0.74), 0.9
	)


func _do_taikou_reveal() -> void:
	var pidx: Array = TaikouAI.choose_play(hand) if tk_bot else tk_marks.duplicate()
	var eidx: Array = TaikouAI.choose_play(enemy_hand)
	pidx.sort()
	eidx.sort()
	tk_player_ids.clear()
	tk_enemy_ids.clear()
	tk_player_reveal.clear()
	tk_enemy_reveal.clear()
	for i in pidx:
		var card: Dictionary = Defs.card(String(hand[i]))
		tk_player_reveal.append(int(card.get("rank", 1)))
		tk_player_ids.append(String(hand[i]))
	for i in eidx:
		var card2: Dictionary = Defs.card(String(enemy_hand[i]))
		tk_enemy_reveal.append(int(card2.get("rank", 1)))
		tk_enemy_ids.append(String(enemy_hand[i]))
	# 满槽 → 本回 3 张牌升 EX（rank+1 封顶 9），消耗后清空；保底见 Rage.best()。
	tk_player_ex = Rage.is_full(tk_player_rage)
	tk_enemy_ex = Rage.is_full(tk_enemy_rage)
	if tk_player_ex:
		var p_ex: Dictionary = Rage.best(tk_player_reveal)
		tk_player_reveal = p_ex["ranks"]
		tk_player_result = p_ex["result"]
		tk_player_ex_boosted = bool(p_ex["boosted"])
		tk_player_rage = 0.0
	else:
		tk_player_result = Rules.evaluate(tk_player_reveal)
		tk_player_ex_boosted = false
	if tk_enemy_ex:
		var e_ex: Dictionary = Rage.best(tk_enemy_reveal)
		tk_enemy_reveal = e_ex["ranks"]
		tk_enemy_result = e_ex["result"]
		tk_enemy_ex_boosted = bool(e_ex["boosted"])
		tk_enemy_rage = 0.0
	else:
		tk_enemy_result = Rules.evaluate(tk_enemy_reveal)
		tk_enemy_ex_boosted = false
	for i in pidx:
		hand[i] = null
	for i in eidx:
		enemy_hand[i] = null
	# 只播动画：perform_visual 不走实时命中判定，伤害留到 _resolve_taikou。
	if tk_player_ids.size() > 0:
		player.perform_visual(String(tk_player_ids[0]))
	if tk_enemy_ids.size() > 0:
		enemy.perform_visual(String(tk_enemy_ids[0]))
	tk_marks.clear()
	tk_phase = "reveal"
	tk_phase_time = 0.0
	_banner(
		"EX 亮牌" if tk_player_ex or tk_enemy_ex else "亮牌",
		"你 %s   ·   青岚 %s" % [String(tk_player_result["name"]), String(tk_enemy_result["name"])],
		Color(0.92, 0.92, 0.98), 1.4
	)


func _resolve_taikou() -> void:
	var cmp: int = Rules.compare(tk_player_result, tk_enemy_result)
	if cmp > 0:
		tk_winner = "player"
		tk_damage = Rules.damage_of(tk_player_result)
		enemy.apply_hit(tk_damage, "taikou", "", false)
		tk_enemy_rage = Rage.gain(tk_enemy_rage, tk_damage)
		_banner(
			"你赢下这一轮",
			"%s · 造成 %d 伤害" % [String(tk_player_result["name"]), tk_damage],
			Color(0.99, 0.76, 0.36), 1.6
		)
	elif cmp < 0:
		tk_winner = "enemy"
		tk_damage = Rules.damage_of(tk_enemy_result)
		player.apply_hit(tk_damage, "taikou", "", false)
		tk_player_rage = Rage.gain(tk_player_rage, tk_damage)
		_banner(
			"青岚赢下这一轮",
			"%s · 受到 %d 伤害" % [String(tk_enemy_result["name"]), tk_damage],
			Color(0.42, 0.80, 0.98), 1.6
		)
	else:
		tk_winner = "draw"
		tk_damage = 3
		player.apply_hit(3, "taikou", "", false)
		enemy.apply_hit(3, "taikou", "", false)
		tk_player_rage = Rage.gain(tk_player_rage, 3)
		tk_enemy_rage = Rage.gain(tk_enemy_rage, 3)
		_banner("平局", "双方各受 3 点", Color(0.86, 0.88, 0.95), 1.6)
	# 验收钩子：只有无输入自动对战才打，正常游玩不产生日志噪音。
	if tk_bot:
		print("[TAIKOU] turn=%d hp=%d/%d rage=%d/%d ex=%s/%s | 你 %s %s vs 青岚 %s %s | winner=%s dmg=%d" % [
			tk_turn, player.hp, enemy.hp,
			int(tk_player_rage), int(tk_enemy_rage),
			"EX" if tk_player_ex else "-", "EX" if tk_enemy_ex else "-",
			String(tk_player_result["name"]), str(tk_player_reveal),
			String(tk_enemy_result["name"]), str(tk_enemy_reveal),
			tk_winner, tk_damage
		])
	tk_phase = "resolve"
	tk_phase_time = 0.0


func _finish_taikou_turn() -> void:
	# 出掉的 3 张统一补回，手牌始终 5 张 —— AI 的穷举才不会读到空格。
	for i in range(hand.size()):
		if hand[i] == null:
			hand[i] = _draw_from(_deck)
	for i in range(enemy_hand.size()):
		if enemy_hand[i] == null:
			enemy_hand[i] = _draw_from(_enemy_deck)
	combo_count = 0
	combo_shown = 0.0
	if player.hp <= 0 or enemy.hp <= 0:
		_end_taikou_round()
		return
	# 先判断是否打满：收局时 tk_turn 停在最后一回，不要自增出超过上限、
	# 根本不存在的轮次（否则 HUD 会显示「第 4 轮 / 共 3 轮」）。
	if tk_turn >= TK_MAX_TURNS:
		var winner := "draw"
		if player.hp > enemy.hp:
			winner = "player"
		elif enemy.hp > player.hp:
			winner = "enemy"
		_end_round(winner, "%d 回战罢 · 按兵力判定" % TK_MAX_TURNS)
		return
	tk_turn += 1
	_reset_taikou_turn(false)


func _end_taikou_round() -> void:
	var winner := "player"
	if player.hp <= 0 and enemy.hp <= 0:
		winner = "player" if player.hp >= enemy.hp else "enemy"
	elif player.hp <= 0:
		winner = "enemy"
	_end_round(winner, "K.O.")



# ── 实时格斗：出牌（realtime 兜底） ────────────────────

func _try_play(index: int) -> void:
	if round_phase != "fight" or paused:
		return
	if index < 0 or index >= hand.size():
		return
	var id: Variant = hand[index]
	if id == null:
		return
	var card := Defs.card(String(id))
	if int(card.get("cost", 0)) > int(player.meter):
		_push_float_text(player.position + Vector2(0, -210), "气不足", Color(0.85, 0.42, 0.42))
		return
	if player.play_card(String(id)):
		hand[index] = null
		cooldowns[index] = COOLDOWN_TOTAL
		selected_index = -1
		if demo_ai != null:
			demo_ai.note_played(String(id))


func _try_enemy_play(index: int) -> void:
	if round_phase != "fight" or index < 0 or index >= enemy_hand.size():
		return
	var id: Variant = enemy_hand[index]
	if id == null:
		return
	if enemy.play_card(String(id)):
		enemy_hand[index] = null
		enemy_cooldowns[index] = COOLDOWN_TOTAL
		ai.note_played(String(id))


func _on_card_played(_card_id: String, _owner_is_player: bool) -> void:
	selected_index = -1


# ── 命中表现 ────────────────────────────────────────────────

func _on_hit_confirmed(attacker_is_player: bool, damage: int, blocked: bool, dodged: bool) -> void:
	var victim = enemy if attacker_is_player else player
	var attacker = player if attacker_is_player else enemy
	var at: Vector2 = victim.position + Vector2(0, -112)

	if dodged:
		_push_ring(at, Color(0.72, 0.92, 1.0), 0.22)
		_push_float_text(at + Vector2(0, -26), "闪避", Color(0.72, 0.92, 1.0))
		if victim == player:
			player.on_dodged_successfully()
		return

	if blocked:
		_push_ring(at, Color(0.58, 0.74, 0.98), 0.2)
		_push_float_text(at + Vector2(0, -20), "格挡 %d" % damage, Color(0.68, 0.82, 1.0))
		_global_hitstop = 0.045
		_shake = maxf(_shake, 3.5)
		return

	# 命中
	_push_spark(at, attacker_is_player)
	# 数字往上顶到头顶之外：落在躯干上会被浅色的身体吃掉一半。
	_push_float_text(
		at + Vector2(0, -78), str(damage),
		Color(1.0, 0.90, 0.62) if attacker_is_player else Color(1.0, 0.74, 0.70)
	)
	if _capture_on_hit and not _hit_shot_taken:
		_hit_shot_taken = true
		_capture_hit_shot()
	_push_ring(at, Color(1.0, 0.92, 0.72) if attacker_is_player else Color(0.72, 0.9, 1.0), 0.26)
	_global_hitstop = 0.07
	_shake = maxf(_shake, 5.0 + minf(6.0, float(damage) * 0.35))

	if attacker_is_player:
		combo_count += 1
		combo_shown = 1.1
		_combo_timer = 1.4
		var name: String = player.combo_name()
		if name != "":
			_banner(name, "+%d 伤害" % player.combo_bonus(), Color(1.0, 0.78, 0.38), 0.7)
		if player.combo_bonus() > 0:
			_global_hitstop = 0.12
	else:
		combo_count = 0
		combo_shown = 0.0


func _on_super_confirmed(card_name: String, owner_is_player: bool) -> void:
	_flash = 0.75
	_shake = 16.0
	_slowmo = 0.5
	_global_hitstop = 0.24
	var title := card_name if card_name != "" else "大招"
	_banner(
		"大招 · " + title,
		"" if not owner_is_player else "三张牌接上了",
		Color(1.0, 0.72, 0.28) if owner_is_player else Color(0.42, 0.86, 1.0),
		1.1
	)


# ── 投射物 ──────────────────────────────────────────────────

func _on_projectile_requested(origin: Vector2, damage: int, direction: int, owner_name: String) -> void:
	projectiles.append({
		"pos": origin,
		"dir": direction,
		"damage": damage,
		"owner_is_player": owner_name == player.display_name,
		"t": 0.0,
	})


func _tick_projectiles(dt: float) -> void:
	var speed := 640.0
	for i in range(projectiles.size() - 1, -1, -1):
		var p: Dictionary = projectiles[i]
		p["t"] = float(p["t"]) + dt
		p["pos"] = (p["pos"] as Vector2) + Vector2(speed * float(p["dir"]) * dt, 0)
		var pos: Vector2 = p["pos"]
		var is_player_shot: bool = bool(p["owner_is_player"])
		var target = enemy if is_player_shot else player
		# 只看水平距离：横版格斗里没有纵向判定，加一条 y 条件只会让波从胸口
		# 飞过去打不中（第一版就是这么写的，波永远穿身而过）。
		if absf(target.position.x - pos.x) < 46.0:
			target.apply_hit(int(p["damage"]), "wave", "", false)
			_push_ring(pos, Color(0.62, 0.9, 1.0), 0.3)
			projectiles.remove_at(i)
			continue
		if pos.x < -60.0 or pos.x > 1340.0 or float(p["t"]) > 2.6:
			projectiles.remove_at(i)


# ── 特效 ────────────────────────────────────────────────────

func _push_spark(at: Vector2, from_player: bool) -> void:
	var color := Color(1.0, 0.86, 0.52) if from_player else Color(0.62, 0.9, 1.0)
	for i in range(9):
		var angle := randf_range(-PI, PI)
		var speed := randf_range(90.0, 320.0)
		effects.append({
			"kind": "spark",
			"pos": at,
			"vel": Vector2(cos(angle), sin(angle)) * speed,
			"t": 0.0,
			"life": randf_range(0.18, 0.34),
			"color": color,
		})


func _push_ring(at: Vector2, color: Color, life: float) -> void:
	effects.append({"kind": "ring", "pos": at, "t": 0.0, "life": life, "color": color})


func _push_float_text(at: Vector2, text: String, color: Color) -> void:
	# 同一句话在同一位置连着喊会叠成一团乱码（自动对战刷出过两条完全重合的
	# 「气不足」）。短时间内的重复直接丢掉，其他的左右抖开一点。
	for e: Dictionary in effects:
		if String(e["kind"]) != "text":
			continue
		if String(e["text"]) == text and float(e["t"]) < 0.3:
			return
	var jitter := Vector2(randf_range(-22.0, 22.0), randf_range(-6.0, 6.0))
	effects.append({"kind": "text", "pos": at + jitter, "text": text, "t": 0.0, "life": 0.72, "color": color})


func _tick_effects(dt: float) -> void:
	for i in range(effects.size() - 1, -1, -1):
		var e: Dictionary = effects[i]
		e["t"] = float(e["t"]) + dt
		if e["kind"] == "spark":
			e["pos"] = (e["pos"] as Vector2) + (e["vel"] as Vector2) * dt
			e["vel"] = (e["vel"] as Vector2) * (1.0 - dt * 4.0)
		if float(e["t"]) >= float(e["life"]):
			effects.remove_at(i)


func _banner(text: String, sub: String, color: Color, hold: float) -> void:
	banner_text = text
	banner_sub = sub
	banner_color = color
	banner_time = maxf(hold, 0.6)


func _shake_offset() -> Vector2:
	if _shake <= 0.05:
		return Vector2.ZERO
	return Vector2(randf_range(-1.0, 1.0), randf_range(-1.0, 1.0)) * _shake


# ── 输入 ────────────────────────────────────────────────────

func _unhandled_input(event: InputEvent) -> void:
	if not (event is InputEventKey) or not event.pressed or event.echo:
		return
	var key: int = (event as InputEventKey).keycode
	if battle_mode == "taikou" and round_phase == "fight":
		match key:
			KEY_1, KEY_2, KEY_3, KEY_4, KEY_5:
				if not tk_bot:
					_taikou_toggle(key - KEY_1)
			KEY_SPACE, KEY_ENTER:
				if not tk_bot:
					_taikou_confirm()
			KEY_R:
				_start_match()
			KEY_P:
				paused = not paused
		return
	match key:
		KEY_1, KEY_2, KEY_3, KEY_4, KEY_5:
			_try_play(key - KEY_1)
		KEY_R:
			_start_match()
		KEY_SPACE:
			paused = not paused


# ── 绘制 ────────────────────────────────────────────────────

func _draw() -> void:
	var offset: Vector2 = _shake_offset()
	draw_set_transform(offset)
	_draw_backdrop()
	draw_set_transform(Vector2.ZERO)

	if _flash > 0.01:
		draw_rect(Rect2(-40, -40, 1360, 800), Color(1, 0.98, 0.92, _flash * 0.55))


## 由 fx_layer 在自己的 _draw 里回调。画在角色之上，跟着震屏一起抖。
func paint_fx(canvas: CanvasItem) -> void:
	for e: Dictionary in effects:
		_draw_effect(canvas, e)


func paint_projectiles(canvas: CanvasItem) -> void:
	for p: Dictionary in projectiles:
		_draw_projectile(canvas, p)


func _build_backdrop() -> void:
	# 城市剪影是静态的，生成一次存下来，别每帧重算。
	var rng := RandomNumberGenerator.new()
	rng.seed = 20261031
	var far: Array = []
	var near: Array = []
	var x := -40.0
	while x < 1340.0:
		var w := rng.randf_range(38.0, 96.0)
		var h := rng.randf_range(60.0, 210.0)
		# 底边压到地平线以下：楼是「站在擂台后面」，不是浮在半空。
		far.append(Rect2(x, GROUND_Y + 12.0 - h, w, h))
		x += w + rng.randf_range(6.0, 18.0)
	x = -30.0
	while x < 1340.0:
		var w := rng.randf_range(50.0, 130.0)
		var h := rng.randf_range(40.0, 140.0)
		near.append(Rect2(x, GROUND_Y + 28.0 - h, w, h))
		x += w + rng.randf_range(10.0, 26.0)

	var lamps: Array = []
	for i in range(46):
		lamps.append(Vector2(rng.randf_range(0.0, 1280.0), rng.randf_range(GROUND_Y - 250.0, GROUND_Y - 60.0)))

	_background_cache = {"far": far, "near": near, "lamps": lamps}


func _draw_backdrop() -> void:
	# 夜空：八条横向色带当渐变。比 shader 便宜，也足够读。
	var bands := [
		Color(0.035, 0.045, 0.085),
		Color(0.055, 0.055, 0.115),
		Color(0.085, 0.062, 0.145),
		Color(0.120, 0.070, 0.175),
		Color(0.155, 0.078, 0.190),
		Color(0.185, 0.090, 0.180),
	]
	for i in range(bands.size()):
		var y := float(i) * 78.0
		draw_rect(Rect2(-40, y, 1360, 80), bands[i])

	# 月亮：一个低对比的圆，给画面一个光源方向。
	draw_circle(Vector2(1040, 120), 74.0, Color(0.96, 0.92, 0.82, 0.10))
	draw_circle(Vector2(1040, 120), 52.0, Color(0.98, 0.94, 0.84, 0.14))

	# 远景楼群
	for rect: Rect2 in _background_cache["far"]:
		draw_rect(rect, Color(0.075, 0.080, 0.135, 0.95))
	# 近景楼群 + 零星窗口
	for rect: Rect2 in _background_cache["near"]:
		draw_rect(rect, Color(0.045, 0.050, 0.085, 1.0))

	var lamp_color := Color(1.0, 0.80, 0.45, 0.55)
	for pos: Vector2 in _background_cache["lamps"]:
		var flicker := 0.55 + 0.45 * sin(_time * 1.7 + pos.x * 0.03)
		draw_rect(Rect2(pos.x, pos.y, 3.0, 3.0), Color(lamp_color.r, lamp_color.g, lamp_color.b, lamp_color.a * flicker))

	# 图像背景盖掉上面那套程序化色带/剪影；玩法图层（聚光灯、地板线、
	# 边界柱、脚下反光）仍画在它之上。注释掉这两行即回到纯代码背景。
	draw_texture_rect(BackdropTexture, Rect2(-40, -40, 1360, 800), false)
	draw_rect(Rect2(-40, -40, 1360, 800), Color(0.055, 0.045, 0.085, 0.20))

	# 聚光灯锥：从顶部两侧打到擂台中央。
	_draw_light_cone(Vector2(250, -40), Vector2(430, GROUND_Y), Color(1.0, 0.72, 0.42, 0.055))
	_draw_light_cone(Vector2(1030, -40), Vector2(850, GROUND_Y), Color(0.42, 0.78, 1.0, 0.055))

	# 擂台地面
	draw_rect(Rect2(-40, GROUND_Y, 1360, 240), Color(0.075, 0.062, 0.090))
	draw_rect(Rect2(-40, GROUND_Y, 1360, 3.0), Color(0.42, 0.34, 0.40, 0.6))

	# 透视地板线：越远越密，往画面外收。
	for i in range(9):
		var t := float(i) / 8.0
		var y := GROUND_Y + 4.0 + pow(t, 1.7) * 200.0
		draw_line(Vector2(-40, y), Vector2(1320, y), Color(0.40, 0.32, 0.40, 0.16), 1.0)
	for i in range(13):
		var x_bottom := -80.0 + float(i) * 120.0
		var x_top := 640.0 + (x_bottom - 640.0) * 0.30
		draw_line(
			Vector2(x_top, GROUND_Y + 2.0), Vector2(x_bottom, 760.0),
			Color(0.40, 0.32, 0.40, 0.13), 1.0
		)

	# 左右边界：两根发光的柱子，暗示「出不去」。
	draw_rect(Rect2(96, GROUND_Y - 300.0, 6, 300.0), Color(0.55, 0.46, 0.60, 0.22))
	draw_rect(Rect2(1178, GROUND_Y - 300.0, 6, 300.0), Color(0.55, 0.46, 0.60, 0.22))

	# 两名角色脚下的反光，颜色跟角色一致，让站位一眼可读。
	_draw_floor_glow(player.position.x, Color(1.0, 0.62, 0.26, 0.16))
	_draw_floor_glow(enemy.position.x, Color(0.32, 0.76, 0.96, 0.16))


func _draw_light_cone(from: Vector2, to: Vector2, color: Color) -> void:
	var left := PackedVector2Array([from + Vector2(-26, 0), from + Vector2(26, 0), to + Vector2(190, 0), to + Vector2(-190, 0)])
	draw_colored_polygon(left, color)


func _draw_floor_glow(cx: float, color: Color) -> void:
	draw_set_transform(Vector2(cx, GROUND_Y + 6.0), 0.0, Vector2(1.0, 0.16))
	draw_circle(Vector2.ZERO, 120.0, color)
	draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)


func _draw_effect(canvas: CanvasItem, e: Dictionary) -> void:
	var t: float = float(e["t"])
	var life: float = float(e["life"])
	var frac: float = clampf(t / life, 0.0, 1.0)
	var color: Color = e["color"]
	match String(e["kind"]):
		"spark":
			color.a = 1.0 - frac
			canvas.draw_line(
				e["pos"], (e["pos"] as Vector2) - (e["vel"] as Vector2) * 0.045, color, 4.0, true
			)
		"ring":
			var r: float = 18.0 + frac * 62.0
			color.a = (1.0 - frac) * 0.85
			canvas.draw_arc(e["pos"], r, 0.0, TAU, 28, color, 3.0 * (1.0 - frac) + 1.0)
		"text":
			var font: Font = hud.font
			var size := 32
			var tw := font.get_string_size(String(e["text"]), HORIZONTAL_ALIGNMENT_LEFT, -1, size).x
			color.a = 1.0 - pow(frac, 2.0)
			var pos: Vector2 = (e["pos"] as Vector2) + Vector2(0, -34.0 * frac)
			# 深色描边四个方向都描一遍：伤害数字会落在浅色的躯干上，
			# 只描一次右下角等于没描，数字直接消失在角色身上。
			var outline := Color(0.06, 0.03, 0.04, color.a * 0.9)
			for offset: Vector2 in [Vector2(-2, 0), Vector2(2, 0), Vector2(0, -2), Vector2(0, 2)]:
				canvas.draw_string(
					font, pos + Vector2(-tw * 0.5, 0) + offset, String(e["text"]),
					HORIZONTAL_ALIGNMENT_LEFT, -1, size, outline
				)
			canvas.draw_string(
				font, pos + Vector2(-tw * 0.5, 0), String(e["text"]),
				HORIZONTAL_ALIGNMENT_LEFT, -1, size, color
			)


func _draw_projectile(canvas: CanvasItem, p: Dictionary) -> void:
	var pos: Vector2 = p["pos"]
	var dir: float = float(p["dir"])
	var from_player: bool = bool(p["owner_is_player"])
	var core := Color(1.0, 0.86, 0.52) if from_player else Color(0.56, 0.9, 1.0)
	var glow := Color(core.r, core.g, core.b, 0.22)
	for i in range(4):
		var trail := pos - Vector2(dir * float(i) * 16.0, 0)
		canvas.draw_circle(trail, 22.0 - float(i) * 4.0, Color(glow.r, glow.g, glow.b, glow.a - float(i) * 0.04))
	canvas.draw_circle(pos, 17.0, core)
	canvas.draw_circle(pos, 9.0, Color(1, 1, 1, 0.9))
