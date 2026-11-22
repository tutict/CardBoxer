extends SceneTree
const ArenaScript = preload("res://scripts/arena.gd")
const Defs = preload("res://scripts/tactical_defs.gd")
const Rules = preload("res://scripts/tactical_rules.gd")
var checks := 0
var failures: Array[String] = []
var a

func _initialize() -> void:
	call_deferred("_run_checks")

func _run_checks() -> void:
	expect(ArenaScript.BATTLE_MODE == "tactical","new game defaults to tactical")
	if not ResourceLoader.exists("res://scripts/tactical_presenter.gd"):
		expect(false,"tactical presentation adapter is not implemented")
		finish()
		return
	var arena_resource = load("res://scripts/arena.gd")
	if not arena_resource.can_instantiate() or not load("res://scripts/tactical_presenter.gd").can_instantiate():
		expect(false,"Arena and presentation adapter must compile")
		finish()
		return
	OS.set_environment("CARD_BOXER_3D","1")
	OS.set_environment("CARD_BOXER_BATTLE_MODE","")
	OS.set_environment("CARD_BOXER_SEED","2026")
	a = ArenaScript.new()
	root.add_child(a)
	if a.player == null:
		a._ready()
	a.set_process(false)
	a.hud.set_process(false)
	expect(a.tactical != null and a.tactical.phase == "loadout","default Arena owns a tactical draft")
	check_human_path()
	check_native_mapping()
	check_terminal_pose()
	check_legacy_modes()
	a.free()
	finish()

func expect(ok: bool,label: String) -> void:
	checks += 1
	if not ok:
		failures.append(label)

func finish() -> void:
	for failure in failures:
		print("FAIL: ",failure)
	print("TACTICAL INTEGRATION CHECK: %d/%d passed" % [checks-failures.size(),checks])
	quit(0 if failures.is_empty() else 1)

func key(code: int) -> void:
	var event := InputEventKey.new()
	event.keycode = code
	event.pressed = true
	a._unhandled_input(event)

func check_human_path() -> void:
	for code in [KEY_3,KEY_1,KEY_2]:
		key(code)
	key(KEY_SPACE)
	a._process(1.1)
	expect(a.tactical.phase == "select" and a.hand.size() == 8,"keyboard draft starts eight-card planning directly")
	var m = a.tactical
	m.state.distance = 0
	m.state.player.jokers = ["shadow","opening","wind"]
	m.hand = ["sidestep","jab","backstep","guard","focus","cross","wave","throw"]
	m.enemy_hand = ["uppercut","cross","guard","jab","focus","wave","throw","rush"]
	m._enemy_indices = [0,1,2,4,7]
	m._enemy_plan = ["uppercut","cross","guard","focus","rush"]
	m.enemy_preview = ["uppercut",null,"guard",null,"rush"]
	var realtime_signals: Array = []
	a.player.hit_confirmed.connect(func(_p,_d,_b,_e): realtime_signals.append(1))
	a.enemy.hit_confirmed.connect(func(_p,_d,_b,_e): realtime_signals.append(1))
	for code in [KEY_1,KEY_2,KEY_3,KEY_4,KEY_5]:
		key(code)
	key(KEY_SPACE)
	expect(a.player.hp == 100 and a.enemy.hp == 100,"reveal cannot deal damage through Arena")
	a._process(1.1)
	expect(m.phase == "resolve" and a.player.hp == 100 and a.enemy.hp == 100,"resolve setup alone causes no damage")
	a._process(0.60)
	expect(a.player.hp == 100 and a.enemy.hp == 100,"successful first-beat dodge preserves HP")
	a._process(1.10)
	expect(a.enemy.hp == 83 and a.player.hp == 100,"five-card pattern and Joker riposte mirrors exactly seventeen damage")
	for i in range(35):
		a._process(0.1)
	expect(a.enemy.hp == 83 and a.player.hp == 100,"later visual ticks do not apply damage twice")
	expect(realtime_signals.is_empty() and a.projectiles.is_empty(),"tactical visuals never leak realtime hit/projectile signals")
	expect(a.player._visual_only and a.enemy._visual_only,"both tactical actors are visual-only")
	key(KEY_P)
	var old_time: float = m.phase_time
	a._process(3.0)
	expect(m.phase_time == old_time and a.paused,"Arena pause freezes tactical clock")
	key(KEY_P)
	key(KEY_R)
	expect(a.tactical.phase == "loadout" and a.player.hp == 100 and a.enemy.hp == 100,"R clears combat and returns to draft")

func check_native_mapping() -> void:
	var library = load("res://scripts/native_motion.gd").new()
	expect(library.load_data(),"existing authored native library loads")
	var presenter = load("res://scripts/tactical_presenter.gd").new()
	presenter.setup(library)
	var match_script = load("res://scripts/tactical_match.gd")
	for id in Defs.card_ids():
		var m = match_script.new(23)
		m.player_plan = [id,"guard","focus","guard","focus"]
		m.enemy_plan = ["jab","guard","focus","guard","focus"]
		m._begin_resolve()
		presenter.begin_beat(m.active_beat)
		m.tick(0.05)
		var snapshot: Dictionary = presenter.sample(m,"player")
		var visual: Dictionary = presenter.native_visual(m,"player")
		expect(snapshot.card_id == Defs.card(id).clip,"semantic action maps to an existing shared action clip: "+id)
		expect(not visual.is_empty() and visual.pose.rotations.size() == 13,"native pose exists for action: "+id)
		expect(not visual.pose.has("error"),"no missing native animation: "+id)

func check_legacy_modes() -> void:
	for mode in ["taikou","realtime"]:
		OS.set_environment("CARD_BOXER_BATTLE_MODE",mode)
		var legacy = ArenaScript.new()
		root.add_child(legacy)
		if legacy.player == null:
			legacy._ready()
		legacy.set_process(false)
		legacy.hud.set_process(false)
		expect(legacy.battle_mode == mode and legacy.hand.size() == 5,"explicit legacy mode preserves five-card economy: "+mode)
		expect(legacy.tactical == null,"legacy modes do not run tactical state machine: "+mode)
		legacy.free()
	OS.set_environment("CARD_BOXER_BATTLE_MODE","")

func check_terminal_pose() -> void:
	key(KEY_R)
	var m = a.tactical
	m.state.player.hp = 3
	m.state.foe.hp = 3
	m.player_plan = ["jab","guard","focus","guard","focus"]
	m.enemy_plan = ["jab","guard","focus","guard","focus"]
	m._begin_resolve()
	a._process(100.0)
	expect(m.phase == "round_over" and m.round_winner == "draw","double KO reaches round-over")
	expect(a.player._ko_time >= 0.5 and a.enemy._ko_time >= 0.5,"combat terminal states stay fully down after resolution")
	var library = load("res://scripts/native_motion.gd").new()
	library.load_data()
	a.tactical_presenter.setup(library)
	var visual: Dictionary = a.tactical_presenter.native_visual(m,"foe")
	expect(is_equal_approx(float(visual.frame),27.0),"native KO does not restart when phase changes")
	key(KEY_R)
