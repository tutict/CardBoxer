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
const MotionP0 = preload("res://scripts/battle_motion_p0.gd")
const Rhythm = preload("res://scripts/battle_rhythm.gd")
const Fighter3DLayerScript = preload("res://scripts/fighter_3d_layer.gd")
const BattlePresentationScript = preload("res://scripts/battle_presentation.gd")

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

# G 路线双轨：3D 表现层默认关，只有 CARD_BOXER_3D 非空才创建。
var use_3d := false
var layer_3d = null
var layer_3d_foe = null
var motion_3d: Dictionary = {}
var motion_3d_foe: Dictionary = {}
var native_library = null
var presentation = null
var last_visuals: Dictionary = {}
var _round_serial := 0
var _visual_random := RandomNumberGenerator.new()
var _defer_taikou_impacts := false
var _taikou_impacts: Array[Dictionary] = []
var _current_projectile_impact: Dictionary = {}
var _contact_fx := false

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
# P0 动作接线：本回实际播出的赢家动作 / 输家受击档，供 HUD 文案、
# bot 日志与 tests/battle_motion_p0_check.gd 逐项核对。
var tk_motion_id := ""        # "" = 亮牌阶段或平局，没播攻击
var tk_react_id := ""         # 规格索引；new:hit_crush 尚未烘
var tk_motion_extra := ""     # 传给 apply_hit 的受击档
var tk_motion_label := ""     # 中文动作名，进 banner
# KOF 式命中节奏（B 路线）：数值全部来自 battle_rhythm_spec.json 生成的
# battle_rhythm.gd；只写 fighter.visual_shift / visual_tilt 这两个**绘制层**
# 字段，不碰 position、伤害、牌型、硬直档与 tk_phase 时长。
var tk_rhythm_t := -1.0       # <0 = 未激活；0..Rhythm.TOTAL_S 为 resolve 内节奏时钟
var tk_rhythm_winner := ""    # player / enemy；平局不激活节奏
var tk_rhythm_hit := false    # 命中瞬间是否已触发过停顿

# ── redraw-on-demand ────────────────────────────────────────────────
# 静止帧不该每帧重发整棵树的绘制命令。判定用「绘制输入快照」：把
# _draw() / paint_fx() / paint_projectiles() 会读的全部状态串成一个键，
# 与上一帧比对，键变才 queue_redraw()。注入式截帧脚本直接改 arena 字段
# 时不需要登记脏标记，下一帧自然被检测出来。
# fighter.gd 不接这一层：呼吸/步态逐帧连续，签名每帧都变，接了零收益。
var redraw_gate_enabled := true   # 验收用可关；关掉即回到原来的逐帧刷
var redraw_stats := {
	"arena_queued": 0, "arena_skipped": 0,
	"fx_queued": 0, "fx_skipped": 0,
	"hud_queued": 0, "hud_skipped": 0,
	"arena_draws": 0, "fx_draws": 0, "hud_draws": 0,
	"arena_draw_us": 0, "fx_draw_us": 0, "hud_draw_us": 0,
}
var _last_arena_key := ""
var _force_redraw := true     # 第一帧 + 外部 force_redraw() 必须真刷


func _ready() -> void:
	_visual_random.randomize()
	var selected_mode := OS.get_environment("CARD_BOXER_BATTLE_MODE")
	if selected_mode in ["taikou", "realtime"]:
		battle_mode = selected_mode
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

	# G 路线双轨：默认关。打开时只替换玩家侧绘制，
	# 判定 / position / HP / 伤害 / 牌型 / 阶段时长一概不碰。
	use_3d = OS.get_environment("CARD_BOXER_3D") != ""
	if use_3d:
		if ResourceLoader.exists("res://scripts/native_motion.gd"):
			native_library = load("res://scripts/native_motion.gd").new()
			if not native_library.load_data():
				push_error("Native 3D motion unavailable; keeping 2D fighters active.")
				return
		else:
			push_error("Native 3D motion script missing; keeping 2D fighters active.")
			return
		presentation = BattlePresentationScript.new()
		presentation.setup(native_library)
		presentation.reset(_round_serial)
		presentation.cue_ready.connect(_on_presentation_cue)
		var mf3 := FileAccess.open("res://data/motion_input.json", FileAccess.READ)
		if mf3 != null:
			var parsed3: Variant = JSON.parse_string(mf3.get_as_text())
			mf3.close()
			if parsed3 is Dictionary:
				motion_3d = parsed3
		# H 路线：两套骨架 rest 不同，旋转中心 apose_points 必须各用各的。
		var mf3f := FileAccess.open("res://data/motion_input_foe.json", FileAccess.READ)
		if mf3f != null:
			var parsed3f: Variant = JSON.parse_string(mf3f.get_as_text())
			mf3f.close()
			if parsed3f is Dictionary:
				motion_3d_foe = parsed3f
		if not motion_3d.is_empty() and not motion_3d_foe.is_empty():
			var l3 := Fighter3DLayerScript.new()
			world.add_child(l3)
			if l3.setup(motion_3d):
				layer_3d = l3
				print("F3D_READY bones=%d cards=%d" % [
					l3.drv.bone_names.size(), motion_3d["cards"].size()])
			else:
				world.remove_child(l3)
				l3.queue_free()
			var lf := Fighter3DLayerScript.new()
			lf.configure("foe", Fighter3DLayerScript.FOE_GLB_PATH,
					Fighter3DLayerScript.DEFAULT_FOE_YAW, false)
			world.add_child(lf)
			if lf.setup(motion_3d_foe):
				layer_3d_foe = lf
				print("F3D_FOE_READY bones=%d" % [
					lf.drv.bone_names.size()])
			else:
				world.remove_child(lf)
				lf.queue_free()
		if layer_3d != null and layer_3d_foe != null:
			player.draw_3d_override = true
			enemy.draw_3d_override = true
		else:
			push_error("Native 3D model setup failed; keeping 2D fighters active.")
			if layer_3d != null: layer_3d.visible = false
			if layer_3d_foe != null: layer_3d_foe.visible = false


# ── P1 动作覆盖：3D 侧亮牌 / 输家受击 / 平局对峙 ───────────────
# 受击轨道与 fighter.gd:1044-1053 同口径：按硬直倾角绝对值 >=0.6
# 选 hit_heavy，否则 hit_light；只有 BLOCKSTUN 才用 block。回合制的
# apply_hit(card_id="taikou") 不会进 BLOCKSTUN，所以这里只会有前两条，
# block 轨道仍烘进表里备用。hit_crush 是 spec 的规格索引、未烘新帧，
# 2D 侧 super 实际也走 hit_heavy，3D 跟它一致，不假装已有 crush。
# REVEAL_S 必须与 _tick_taikou() 里 reveal 的 1.5 秒判定同值；
# 这里只用于把亮牌进度映射到 focus 帧号，不改阶段时长。
const REACT_STUN_TILT := {"": 0.55, "launch": 0.9,
		"stagger": 0.7, "super": 1.2}
const REACT_DURATION_S := {"": 0.26, "launch": 0.42,
		"stagger": 0.5, "super": 0.75}
const REVEAL_S := 1.5


## 输家 / 平局该播哪条受击轨道（只读现有状态，不改判定）。
func _3d_react_track() -> String:
	var tilt := float(REACT_STUN_TILT.get(tk_motion_extra, 0.55))
	return "hit_heavy" if absf(tilt) >= 0.6 else "hit_light"


## 把 0..1 的进度映射到轨道帧号；帧数从动作表读，不写死。
func _3d_frame_of(card: String, t01: float) -> int:
	var n := int(motion_3d["cards"][card]["frames"])
	return clampi(int(clampf(t01, 0.0, 1.0) * float(n - 1)), 0, n - 1)


func _sync_3d_layer_legacy() -> void:
	# 默认关时立刻返回：节奏时钟仍在跑，但 motion_3d 是空的，
	# 继续往下算帧数会撞空字典。G 路线的早退语义必须保留。
	if (layer_3d == null and layer_3d_foe == null) or motion_3d.is_empty():
		return
	var card := "stance"
	var frame := 0
	var foe_card := "stance"
	var foe_frame := 0
	# 显式 bool：Dictionary.has() 返回 Variant，用 := 推断会 Parse Error。
	var has_focus: bool = motion_3d["cards"].has("focus")
	var react := _3d_react_track()
	var has_react: bool = motion_3d["cards"].has(react)

	if tk_phase == "reveal" and has_focus:
		# 亮牌阶段两侧同播 focus，与 2D 的
		# perform_visual(MotionP0.REVEAL_CARD) 同一语义。
		var ff := _3d_frame_of("focus", tk_phase_time / REVEAL_S)
		card = "focus"
		frame = ff
		foe_card = "focus"
		foe_frame = ff
	elif tk_phase == "resolve":
		# 只有赢下本回的一方播攻击（G/H 路线原逻辑，一字未改）。
		if tk_rhythm_t >= 0.0 and tk_motion_id != "" \
				and tk_rhythm_t <= Rhythm.ATTACK_S:
			var n: int = int(motion_3d["cards"][tk_motion_id]["frames"])
			var f := clampi(int(tk_rhythm_t / Rhythm.ATTACK_S * float(n - 1)), 0, n - 1)
			if tk_rhythm_winner == "player":
				card = tk_motion_id
				frame = f
			elif tk_rhythm_winner == "enemy":
				foe_card = tk_motion_id
				foe_frame = f
		# P1：输家 / 平局接上受击轨道。命中瞬间（HIT_AT_S）之后起播，
		# 按 fighter.gd 的四档硬直时长归一化，播完自然回 stance。
		# 平局不启节奏时钟，用 resolve 阶段时钟直接从 0 起播。
		if has_react and tk_winner != "":
			var stun := float(REACT_DURATION_S.get(tk_motion_extra, 0.26))
			var at := tk_phase_time
			if tk_winner != "draw":
				at = tk_rhythm_t - Rhythm.HIT_AT_S
			if at >= 0.0 and at <= stun:
				var fr := _3d_frame_of(react, at / stun)
				if tk_winner == "player":
					foe_card = react
					foe_frame = fr
				elif tk_winner == "enemy":
					card = react
					frame = fr
				else:
					card = react
					frame = fr
					foe_card = react
					foe_frame = fr
	if layer_3d != null:
		layer_3d.position = player.position + player.visual_shift
		layer_3d.apply(card, frame)
	if layer_3d_foe != null:
		layer_3d_foe.position = enemy.position + enemy.visual_shift
		layer_3d_foe.apply(foe_card, foe_frame)


func _native_active() -> bool:
	return presentation != null and native_library != null and native_library.available() and layer_3d != null and layer_3d_foe != null and player.draw_3d_override and enemy.draw_3d_override


func _presentation_context() -> Dictionary:
	return {"mode":battle_mode,"round_phase":round_phase,"global_hitstop":maxf(_global_hitstop,0.0),"pause":paused,"terminal":round_phase in ["over","match_over"],"taikou_phase":tk_phase,"taikou_time":tk_phase_time,"snapshots":{"player":player.presentation_snapshot(),"foe":enemy.presentation_snapshot()}}


func _advance_presentation(dt: float) -> void:
	if not _native_active(): return
	presentation.advance(dt, _presentation_context())
	if battle_mode == "taikou" and not presentation.exchange.is_empty():
		if String(presentation.exchange.get("winner", "")) != "draw":
			tk_rhythm_t = presentation.exchange_time
			tk_rhythm_hit = presentation.contact_emitted
			tk_rhythm_winner = "player" if String(presentation.exchange.get("actor", "")) == "player" else "enemy"


func _sync_3d_layer() -> void:
	if not _native_active(): return
	var context := _presentation_context()
	for role: String in ["player","foe"]:
		var fighter = player if role == "player" else enemy
		var layer = layer_3d if role == "player" else layer_3d_foe
		var visual: Dictionary = presentation.sample(role, fighter.presentation_snapshot(), context)
		if visual.is_empty(): continue
		last_visuals[role] = visual
		if fighter.visual_shift != visual.canvas_shift or not is_equal_approx(fighter.visual_tilt,float(visual.canvas_tilt)):
			fighter.queue_redraw()
		fighter.visual_shift = visual.canvas_shift
		fighter.visual_tilt = visual.canvas_tilt
		layer.position = fighter.position + visual.canvas_shift
		layer.apply_visual(visual)


func _impact_event(attacker_is_player: bool, damage: int, blocked: bool, dodged: bool) -> Dictionary:
	var attacker = player if attacker_is_player else enemy
	var victim = enemy if attacker_is_player else player
	var attack: Dictionary = attacker.presentation_snapshot()
	var struck: Dictionary = victim.presentation_snapshot()
	var event := {"round_id":_round_serial,"actor":"player" if attacker_is_player else "foe","target":"foe" if attacker_is_player else "player","action_seq":attack.action_seq,"clip_id":attack.card_id,"damage":damage,"blocked":blocked,"dodged":dodged,"terminal":victim.hp <= 0,"local_hitstop":struck.local_hitstop,"stun_duration":struck.stun_duration,"source_kind":"taikou" if _defer_taikou_impacts else "melee","attacker_is_player":attacker_is_player}
	if not _current_projectile_impact.is_empty():
		event.merge(_current_projectile_impact, true)
	return event


func _on_presentation_cue(impact: Dictionary) -> void:
	_contact_fx = true
	_emit_hit_fx(bool(impact.get("attacker_is_player", impact.get("actor", "player") == "player")), int(impact.get("damage", 0)), bool(impact.get("blocked", false)), bool(impact.get("dodged", false)),impact.get("contact_point",null))
	_contact_fx = false
	if tk_winner != "draw":
		_global_hitstop = maxf(_global_hitstop, Rhythm.HITSTOP_S)


## Pure visual calibration against the imported native rig and camera. Damage,
## reach and gameplay position remain owned by the existing rule path.
func _calibrate_taikou_contact(actor_role: String,target_role: String,clip: String,terminal: bool) -> Dictionary:
	var attacker = player if actor_role == "player" else enemy
	var target = player if target_role == "player" else enemy
	var attack_layer = layer_3d if actor_role == "player" else layer_3d_foe
	var target_layer = layer_3d if target_role == "player" else layer_3d_foe
	if not attack_layer.has_method("anchor_offset") or not target_layer.has_method("anchor_offset"): return {}
	var contact: float = native_library.contact_frame(actor_role,clip)
	var attack_pose: Dictionary = native_library.sample(actor_role,clip,contact)
	var reaction := "ko" if terminal else _3d_react_track()
	var target_pose: Dictionary = native_library.sample(target_role,reaction,0.0)
	var hand := "rear_hand" if clip == "cross" else ("palms" if clip == "wave" else "lead_hand")
	var direction := 1.0 if actor_role == "player" else -1.0
	var press := Rhythm.press_px(Rhythm.attack_t(Rhythm.HIT_AT_S)) * direction
	var recoil := Vector2(40.0*direction,0.0)
	var tilt := deg_to_rad(9.0)*direction
	var fist: Vector2 = attacker.position+Vector2(press,0.0)+attack_layer.anchor_offset(attack_pose,hand,attacker.facing,0.0)
	var head: Vector2 = target.position+recoil+target_layer.anchor_offset(target_pose,"head",target.facing,tilt)
	var chest: Vector2 = target.position+recoil+target_layer.anchor_offset(target_pose,"chest",target.facing,tilt)
	var height_progress := clampf((fist.y-head.y)/(chest.y-head.y),0.0,1.0) if absf(chest.y-head.y)>0.0001 else 0.5
	var body: Vector2 = head.lerp(chest,height_progress)
	return {"approach_extra_x":body.x-fist.x,"contact_point":body,"contact_hand":hand}


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
	_round_serial += 1
	if presentation != null: presentation.reset(_round_serial)
	last_visuals.clear()
	_taikou_impacts.clear()
	_current_projectile_impact.clear()
	_defer_taikou_impacts = false
	_contact_fx = false
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
	_global_hitstop = 0.0
	_slowmo = 0.0


func _end_round(winner: String, reason: String) -> void:
	if round_phase != "fight":
		return
	if _native_active() and battle_mode == "realtime":
		presentation.capture_terminal({"player":player.presentation_snapshot(),"foe":enemy.presentation_snapshot()})
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


# ── 按需重绘：绘制输入快照 ─────────────────────────────────────

## 外部（截帧/验收脚本）想立刻刷一帧时可以强制；正常流程不需要调。
func force_redraw() -> void:
	_force_redraw = true


## arena 自身 + fx_layer 的全部绘制输入。任何一项变了，两层一起重画。
func _arena_visual_key() -> String:
	# 树还没建完（自检脚本在 _initialize() 里手工 add_child）时不做判定。
	if world == null or fx_layer == null or player == null or enemy == null:
		return "init"
	# 震屏中的 _shake_offset() 每次 _draw() 都 randf_range，缓存的命令会
	# 与新的 world.position 不一致；这段时间必须逐帧重画。
	if _shake > 0.05:
		return "shake:%f" % _time
	var loser_x := 0.0
	var loser_shift := Vector2.ZERO
	if tk_rhythm_winner == "player":
		loser_x = enemy.position.x
		loser_shift = enemy.visual_shift
	elif tk_rhythm_winner == "enemy":
		loser_x = player.position.x
		loser_shift = player.visual_shift
	return str([
		_flash, player.position.x, enemy.position.x,
		world.position.x, world.position.y,
		fx_layer.position.x, fx_layer.position.y,
		effects, projectiles,
		tk_rhythm_t, tk_rhythm_winner, tk_rhythm_hit,
		loser_x, loser_shift.x, loser_shift.y,
		player.visual_shift.x, player.visual_shift.y,
		enemy.visual_shift.x, enemy.visual_shift.y,
	])


func _request_redraw() -> void:
	var key := _arena_visual_key()
	var dirty: bool = (_force_redraw or not redraw_gate_enabled
		or key != _last_arena_key)
	_last_arena_key = key
	_force_redraw = false
	if dirty:
		redraw_stats["arena_queued"] = int(redraw_stats["arena_queued"]) + 1
		redraw_stats["fx_queued"] = int(redraw_stats["fx_queued"]) + 1
		fx_layer.queue_redraw()
		queue_redraw()
	else:
		redraw_stats["arena_skipped"] = int(redraw_stats["arena_skipped"]) + 1
		redraw_stats["fx_skipped"] = int(redraw_stats["fx_skipped"]) + 1


# ── 每帧 ────────────────────────────────────────────────────

func _process(delta: float) -> void:
	_time += delta
	if paused:
		_request_redraw()
		return

	if _global_hitstop > 0.0:
		_advance_presentation(delta)
		_global_hitstop -= delta
		_tick_effects(delta * 0.25)
		world.position = _shake_offset()
		fx_layer.position = world.position
		# 停顿冻结帧也要同步 3D 层：注入式节奏截帧正落在这一段。
		_sync_3d_layer()
		_request_redraw()
		# 命中停顿期间也要允许截帧：KOF 式 HIT! 定格画面正好落在这一段，
		# 旧写法在这里直接 return，_maybe_capture() 永远等不到。
		_maybe_capture()
		return

	var dt := delta
	if _slowmo > 0.0:
		_slowmo -= delta
		dt = delta * 0.35
	if _native_active() and (battle_mode != "taikou" or round_phase != "fight"):
		_advance_presentation(dt)

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

	if round_phase == "fight":
		_tick_projectiles(dt)
	_tick_effects(dt)
	world.position = _shake_offset()
	fx_layer.position = world.position
	_sync_3d_layer()
	_request_redraw()
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
	if presentation != null: presentation.reset(_round_serial)
	last_visuals.clear()
	_taikou_impacts.clear()
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
	tk_motion_id = ""
	tk_react_id = ""
	tk_motion_extra = ""
	tk_motion_label = ""
	tk_rhythm_t = -1.0
	tk_rhythm_winner = ""
	tk_rhythm_hit = false
	_clear_rhythm_visuals()
	_banner(
		"第 %d 轮 · 弃牌" % tk_turn,
		"1-5 标记要换掉的牌（可 0 张） · 空格确认",
		Color(0.96, 0.90, 0.74), 0.9
	)


func _tick_taikou(dt: float) -> void:
	tk_phase_time += dt
	if _native_active():
		_advance_presentation(dt)
	else:
		_tick_rhythm(dt)
		_apply_rhythm_visuals()
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


# ── KOF 式命中节奏（纯表现层） ─────────────────────────────
# 与 side-view-battle-demo/make_side_battle.py 的 ATTACK 段共用同一套数值：
# 110px 三角脉冲前压 / 40px 击退 / 9° 后仰 / 12 道星芒 / 4 条短斜速度线 /
# HIT! 停顿标签。数值只定义在 battle_rhythm_spec.json，生成的 battle_rhythm.gd
# 与离线脚本都由 verify_rhythm.py 逐项对账。
# 视觉位移写进 fighter.visual_shift / visual_tilt，只在 fighter._draw() 的
# draw_set_transform 里生效；position、伤害、牌型、硬直、阶段时长一律不动。

func _tick_rhythm(dt: float) -> void:
	if tk_rhythm_t < 0.0 or tk_rhythm_winner == "":
		return
	var prev := tk_rhythm_t
	tk_rhythm_t += dt
	if not tk_rhythm_hit and prev < Rhythm.HIT_AT_S and tk_rhythm_t >= Rhythm.HIT_AT_S:
		tk_rhythm_hit = true
		# 复用引擎现成的全局停顿：_process 的 hitstop 分支会让 _tick_taikou
		# 整段停跑，节奏时钟与角色绘制一起定格 —— 正是离线 HITSTOP 3 帧口径。
		_global_hitstop = maxf(_global_hitstop, Rhythm.HITSTOP_S)
	if tk_rhythm_t > Rhythm.TOTAL_S:
		tk_rhythm_t = -1.0
		tk_rhythm_winner = ""
		tk_rhythm_hit = false


func _clear_rhythm_visuals() -> void:
	if player != null:
		player.visual_shift = Vector2.ZERO
		player.visual_tilt = 0.0
		player.queue_redraw()
	if enemy != null:
		enemy.visual_shift = Vector2.ZERO
		enemy.visual_tilt = 0.0
		enemy.queue_redraw()


func _apply_rhythm_visuals() -> void:
	var fade := Rhythm.fade_at(tk_rhythm_t)
	if fade <= 0.0 or tk_rhythm_winner == "":
		_clear_rhythm_visuals()
		return
	var t := Rhythm.attack_t(tk_rhythm_t)
	var dir := 1.0 if tk_rhythm_winner == "player" else -1.0
	var winner: Fighter = player if tk_rhythm_winner == "player" else enemy
	var loser: Fighter = enemy if tk_rhythm_winner == "player" else player
	var frame := tk_rhythm_t / Rhythm.FRAME_S
	var shake_x := Rhythm.SHAKE_AMP_PX * sin(frame * Rhythm.SHAKE_FREQ_X_PER_FRAME)
	var shake_y := Rhythm.SHAKE_AMP_PX * sin(frame * Rhythm.SHAKE_FREQ_Y_PER_FRAME)
	winner.visual_shift = Vector2(Rhythm.press_px(t) * dir * fade, 0.0)
	winner.visual_tilt = 0.0
	loser.visual_shift = Vector2(
		(Rhythm.knock_px(t) * dir + shake_x) * fade, shake_y * fade)
	# 离线语义：foe 输 +9°、player 输 -9°；dir 正好是赢家朝向，
	# 所以后仰角与 dir 同号，不是反号。
	loser.visual_tilt = Rhythm.tilt_rad(t) * dir * fade
	winner.queue_redraw()
	loser.queue_redraw()


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
	# P1 亮牌阶段不打架：两侧统一播 focus 起势（reuse:card:focus），
	# 不取 tk_*_ids[0]、不播任何招式。perform_visual 同时把角色置为
	# _visual_only，亮牌阶段因此不可能漏进实时命中判定；伤害与攻击动作
	# 一律等到 _resolve_taikou()（spec: reveal → 比牌型 → resolve 结算）。
	# EX 专属的 ex_charge / reveal_present 标 new: 尚未烘，这里不假装已有。
	if tk_player_ids.size() > 0:
		player.perform_visual(MotionP0.REVEAL_CARD)
	if tk_enemy_ids.size() > 0:
		enemy.perform_visual(MotionP0.REVEAL_CARD)
	tk_marks.clear()
	tk_phase = "reveal"
	tk_phase_time = 0.0
	_banner(
		"EX 亮牌" if tk_player_ex or tk_enemy_ex else "亮牌",
		"你 %s   ·   青岚 %s" % [String(tk_player_result["name"]), String(tk_enemy_result["name"])],
		Color(0.92, 0.92, 0.98), 1.4
	)


func _resolve_taikou() -> void:
	_defer_taikou_impacts = _native_active()
	_taikou_impacts.clear()
	var cmp: int = Rules.compare(tk_player_result, tk_enemy_result)
	# P2/P3：动作强度由**赢家牌型**决定，退役 tk_*_ids[0]；只有赢家播
	# 攻击、输家只播受击，平局两边都不播攻击。extra 交给 fighter.gd 的
	# apply_hit()，对应已有 0.26 / 0.42 / 0.75s 硬直四档（G4）。
	# 伤害公式仍走 Rules.damage_of()，接线不改数值。
	var winner_type := ""
	if cmp > 0:
		winner_type = String(tk_player_result.get("type", ""))
	elif cmp < 0:
		winner_type = String(tk_enemy_result.get("type", ""))
	var bind: Dictionary = MotionP0.binding_for(winner_type)
	tk_motion_id = "" if winner_type == "" else String(bind["winner_card"])
	tk_react_id = String(MotionP0.DRAW["react"]) if winner_type == "" else String(bind["react"])
	tk_motion_extra = String(MotionP0.DRAW["extra"]) if winner_type == "" else String(bind["extra"])
	tk_motion_label = MotionP0.label_of(winner_type)
	if cmp > 0:
		tk_winner = "player"
		tk_damage = Rules.damage_of(tk_player_result)
		player.perform_visual(tk_motion_id)
		enemy.apply_hit(tk_damage, "taikou", tk_motion_extra, false)
		tk_enemy_rage = Rage.gain(tk_enemy_rage, tk_damage)
		_banner(
			"你赢下这一轮",
			"%s · %s · 造成 %d 伤害" % [String(tk_player_result["name"]), tk_motion_label, tk_damage],
			Color(0.99, 0.76, 0.36), 1.6
		)
	elif cmp < 0:
		tk_winner = "enemy"
		tk_damage = Rules.damage_of(tk_enemy_result)
		enemy.perform_visual(tk_motion_id)
		player.apply_hit(tk_damage, "taikou", tk_motion_extra, false)
		tk_player_rage = Rage.gain(tk_player_rage, tk_damage)
		_banner(
			"青岚赢下这一轮",
			"%s · %s · 受到 %d 伤害" % [String(tk_enemy_result["name"]), tk_motion_label, tk_damage],
			Color(0.42, 0.80, 0.98), 1.6
		)
	else:
		tk_winner = "draw"
		tk_damage = 3
		player.apply_hit(3, "taikou", tk_motion_extra, false)
		enemy.apply_hit(3, "taikou", tk_motion_extra, false)
		tk_player_rage = Rage.gain(tk_player_rage, 3)
		tk_enemy_rage = Rage.gain(tk_enemy_rage, 3)
		_banner("平局", "双方各受 3 点 · %s" % tk_motion_label, Color(0.86, 0.88, 0.95), 1.6)
	# 验收钩子：只有无输入自动对战才打，正常游玩不产生日志噪音。
	_defer_taikou_impacts = false
	if _native_active():
		var actor := "player" if tk_winner == "player" else "foe"
		var attacker = player if actor == "player" else enemy
		var target_role := "foe" if actor == "player" else "player"
		var terminal: bool = player.hp <= 0 or enemy.hp <= 0
		var exchange := {"round_id":_round_serial,"winner":tk_winner,"actor":actor if tk_winner != "draw" else "","target":target_role,"clip_id":tk_motion_id,"action_seq":attacker.presentation_snapshot().action_seq,"terminal":terminal,"extra":tk_motion_extra,"impacts":_taikou_impacts}
		if tk_winner != "draw":
			var calibration := _calibrate_taikou_contact(actor,target_role,tk_motion_id,terminal)
			exchange.merge(calibration,true)
			for impact: Dictionary in _taikou_impacts: impact.merge(calibration,true)
		presentation.begin_exchange(exchange)
	if tk_bot:
		print("[TAIKOU] turn=%d hp=%d/%d rage=%d/%d ex=%s/%s | 你 %s %s vs 青岚 %s %s | winner=%s dmg=%d motion=%s react=%s extra=%s" % [
			tk_turn, player.hp, enemy.hp,
			int(tk_player_rage), int(tk_enemy_rage),
			"EX" if tk_player_ex else "-", "EX" if tk_enemy_ex else "-",
			String(tk_player_result["name"]), str(tk_player_reveal),
			String(tk_enemy_result["name"]), str(tk_enemy_reveal),
			tk_winner, tk_damage, tk_motion_id, tk_react_id, tk_motion_extra
		])
	# 节奏层只在分出胜负时启动；平局保持 P0 已落地的「对峙」表现。
	tk_rhythm_hit = false
	if tk_winner == "draw":
		tk_rhythm_t = -1.0
		tk_rhythm_winner = ""
	else:
		tk_rhythm_t = 0.0
		tk_rhythm_winner = tk_winner
	_apply_rhythm_visuals()
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
	if _native_active():
		var impact := _impact_event(attacker_is_player, damage, blocked, dodged)
		if _defer_taikou_impacts:
			_taikou_impacts.append(impact)
			return
		presentation.record_impact(impact)
	_emit_hit_fx(attacker_is_player, damage, blocked, dodged)


func _emit_hit_fx(attacker_is_player: bool, damage: int, blocked: bool, dodged: bool,contact_point: Variant = null) -> void:
	var victim = enemy if attacker_is_player else player
	var attacker = player if attacker_is_player else enemy
	var at: Vector2 = victim.position + Vector2(0, -112)
	if _native_active():
		var role := "foe" if attacker_is_player else "player"
		var visual: Dictionary = presentation.sample(role,victim.presentation_snapshot(),_presentation_context())
		if not visual.is_empty():
			var layer = layer_3d_foe if attacker_is_player else layer_3d
			at = victim.position + visual.canvas_shift + layer.anchor_offset(visual.pose,"chest",visual.facing,visual.canvas_tilt)
		if contact_point is Vector2: at = contact_point

	if dodged:
		_push_ring(at, Color(0.72, 0.92, 1.0), 0.22)
		_push_float_text(at + Vector2(0, -26), "闪避", Color(0.72, 0.92, 1.0))
		if victim == player:
			player.on_dodged_successfully()
		return

	if blocked:
		_push_ring(at, Color(0.58, 0.74, 0.98), 0.2)
		_push_float_text(at + Vector2(0, -20), "格挡 %d" % damage, Color(0.68, 0.82, 1.0))
		if not _contact_fx: _global_hitstop = 0.045
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
	if not _contact_fx: _global_hitstop = 0.07
	_shake = maxf(_shake, 5.0 + minf(6.0, float(damage) * 0.35))

	if attacker_is_player:
		combo_count += 1
		combo_shown = 1.1
		_combo_timer = 1.4
		var name: String = player.combo_name()
		if name != "":
			_banner(name, "+%d 伤害" % player.combo_bonus(), Color(1.0, 0.78, 0.38), 0.7)
		if player.combo_bonus() > 0 and not _contact_fx:
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
	var owner = player if owner_name == player.display_name else enemy
	var snapshot: Dictionary = owner.presentation_snapshot()
	if _native_active():
		presentation.record_impact({"round_id":_round_serial,"actor":"player" if owner.is_player else "foe","target":"foe" if owner.is_player else "player","action_seq":snapshot.action_seq,"clip_id":"wave","source_kind":"release"})
	projectiles.append({
		"pos": origin,
		"dir": direction,
		"damage": damage,
		"owner_is_player": owner_name == player.display_name,
		"t": 0.0,
		"round_id":_round_serial,
		"action_seq":snapshot.action_seq,
	})


func _tick_projectiles(dt: float) -> void:
	if round_phase != "fight": return
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
			_current_projectile_impact = {"round_id":p.get("round_id", _round_serial),"action_seq":p.get("action_seq", 0),"clip_id":"wave","source_kind":"projectile"}
			target.apply_hit(int(p["damage"]), "wave", "", false)
			_current_projectile_impact.clear()
			_push_ring(pos, Color(0.62, 0.9, 1.0), 0.3)
			projectiles.remove_at(i)
			if player.hp <= 0 or enemy.hp <= 0:
				_end_round("player" if enemy.hp <= 0 else "enemy", "K.O.")
				return
			continue
		if pos.x < -60.0 or pos.x > 1340.0 or float(p["t"]) > 2.6:
			projectiles.remove_at(i)


# ── 特效 ────────────────────────────────────────────────────

func _push_spark(at: Vector2, from_player: bool) -> void:
	var color := Color(1.0, 0.86, 0.52) if from_player else Color(0.62, 0.9, 1.0)
	for i in range(9):
		var angle := _visual_random.randf_range(-PI, PI)
		var speed := _visual_random.randf_range(90.0, 320.0)
		effects.append({
			"kind": "spark",
			"pos": at,
			"vel": Vector2(cos(angle), sin(angle)) * speed,
			"t": 0.0,
			"life": _visual_random.randf_range(0.18, 0.34),
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
	var jitter := Vector2(_visual_random.randf_range(-22.0, 22.0), _visual_random.randf_range(-6.0, 6.0))
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
	return Vector2(_visual_random.randf_range(-1.0, 1.0), _visual_random.randf_range(-1.0, 1.0)) * _shake


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
	var t0 := Time.get_ticks_usec()
	redraw_stats["arena_draws"] = int(redraw_stats["arena_draws"]) + 1
	var offset: Vector2 = _shake_offset()
	draw_set_transform(offset)
	_draw_backdrop()
	draw_set_transform(Vector2.ZERO)

	if _flash > 0.01:
		draw_rect(Rect2(-40, -40, 1360, 800), Color(1, 0.98, 0.92, _flash * 0.55))
	redraw_stats["arena_draw_us"] = int(redraw_stats["arena_draw_us"]) + (Time.get_ticks_usec() - t0)


## 由 fx_layer 在自己的 _draw 里回调。画在角色之上，跟着震屏一起抖。
func paint_fx(canvas: CanvasItem) -> void:
	for e: Dictionary in effects:
		_draw_effect(canvas, e)
	_draw_rhythm_fx(canvas)


func _rhythm_contact_point() -> Vector2:
	if _native_active() and presentation.exchange.get("contact_point",null) is Vector2:
		return presentation.exchange["contact_point"]
	var loser: Fighter = enemy if tk_rhythm_winner == "player" else player
	return Vector2(loser.position.x+loser.visual_shift.x,Rhythm.GAME_GROUND_Y+Rhythm.GAME_SPARK_Y_OFFSET)


## 节奏层的三种纯绘制特效，画在 fx_layer（角色之后、HUD 之前）。
## 不进 effects 队列：它们由节奏时钟解析式决定，重复帧必须完全一致。
func _draw_rhythm_fx(canvas: CanvasItem) -> void:
	if tk_rhythm_t < 0.0 or tk_rhythm_winner == "":
		return
	var t := Rhythm.attack_t(tk_rhythm_t)
	var dir := 1.0 if tk_rhythm_winner == "player" else -1.0
	# 4 条短淡斜线，只在两人空隙、只在攻击窗前半段（离线 draw_speed_lines）。
	if Rhythm.speed_active(tk_rhythm_t):
		var line_col := Color(1.0, 0.925, 0.784, Rhythm.speed_alpha01(t))
		for k in range(int(Rhythm.SPEED_LINE_COUNT)):
			var y := Rhythm.GAME_SPEED_LINE_Y0 + float(k) * Rhythm.SPEED_LINE_Y_STEP
			var length := Rhythm.speed_len(t, k)
			var x0 := Rhythm.GAME_SPEED_LINE_MID_X - dir * length * 0.5
			canvas.draw_line(
				Vector2(x0, y),
				Vector2(x0 + dir * length, y - Rhythm.SPEED_LINE_DY * dir),
				line_col, 1.0)
	# 白色核心 + 12 道放射星芒，命中帧起 3 帧尾窗（离线 draw_spark）。
	if Rhythm.spark_active(tk_rhythm_t):
		var st := clampf(
			(tk_rhythm_t - Rhythm.HIT_AT_S) / (Rhythm.FRAME_S * Rhythm.SPARK_TAIL_FRAMES),
			0.0, 1.0)
		var a := Rhythm.spark_alpha01(st)
		# 必须显式标注：untyped Variant 上的 .position 推不出 := 的类型。
		var contact := _rhythm_contact_point()
		var hx := contact.x
		var hy := contact.y
		var r := Rhythm.SPARK_RADIUS_BASE_PX + Rhythm.SPARK_RADIUS_GROWTH_PX * st
		canvas.draw_circle(Vector2(hx, hy), Rhythm.SPARK_CORE_PX,
			Color(1.0, 0.988, 0.91, a))
		for k in range(int(Rhythm.SPARK_RAYS)):
			var ang := TAU * float(k) / Rhythm.SPARK_RAYS + Rhythm.SPARK_RAY_PHASE
			var r0 := r * Rhythm.SPARK_RAY_INNER_RATIO
			var r1 := r + Rhythm.SPARK_RAY_EXT_PX * (1.0 - st)
			var p0 := Vector2(hx + r0 * cos(ang), hy + r0 * sin(ang))
			var p1 := Vector2(hx + r1 * cos(ang), hy + r1 * sin(ang))
			var w := Rhythm.SPARK_RAY_WIDTH_MAIN if k % 3 == 0 else Rhythm.SPARK_RAY_WIDTH_SUB
			canvas.draw_line(p0, p1, Color(1.0, 0.87, 0.58, a), w)
	# HIT!：停顿帧与命中帧共用同一渲染参数，只多这一个标签。
	if Rhythm.hit_label_active(tk_rhythm_t):
		canvas.draw_string(
			ThemeDB.fallback_font, Rhythm.GAME_HIT_LABEL_POS,
			Rhythm.HITSTOP_LABEL, HORIZONTAL_ALIGNMENT_CENTER, -1,
			int(Rhythm.GAME_HIT_LABEL_SIZE), Color(1.0, 0.886, 0.659))


func paint_projectiles(canvas: CanvasItem) -> void:
	for p: Dictionary in projectiles:
		_draw_projectile(canvas, p)


func _draw_backdrop() -> void:
	# 引擎优化：原先这里先画整套程序化夜空 / 月亮 / 楼群 / 闪烁灯窗，
	# 紧接着又被下面这张不透明的 arena.png 完全盖掉 —— 每帧纯浪费。
	# 贴图是 RGB（无 alpha），Rect2(-40,-40,1360,800) 覆盖整个 1280x720
	# 视口，删掉被覆盖的绘制不改变任何像素；A/B 证据见 engine-optimization/。
	# 若要换回程序化背景，从 orig/pre-engine-opt/arena.gd 取回旧段。
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
