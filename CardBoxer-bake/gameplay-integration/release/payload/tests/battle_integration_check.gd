extends SceneTree
const ArenaScript = preload("res://scripts/arena.gd")
const Rules = preload("res://scripts/taikou_rules.gd")
var failures: Array[String] = []
var total := 0

func expect(ok: bool, label: String) -> void:
	total += 1
	if not ok: failures.append(label)

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var a = ArenaScript.new()
	root.add_child(a)
	if a.player == null: a._ready()
	a.set_process(false)
	var configured := OS.get_environment("CARD_BOXER_BATTLE_MODE")
	expect(a.battle_mode == configured if configured in ["tactical","taikou","realtime"] else a.battle_mode == "tactical", "startup battle mode follows environment with tactical default")
	seed(9819)
	var expected := randi()
	seed(9819)
	a._push_spark(Vector2.ZERO, true)
	a._push_float_text(Vector2.ZERO, "rng-check", Color.WHITE)
	a._shake = 5.0
	a._shake_offset()
	expect(randi() == expected, "spark/text/shake do not consume gameplay RNG")
	if a.has_method("_native_active") and a._native_active():
		a.battle_mode = "taikou"
		a._start_round()
		a.round_phase = "fight"
		a.tk_player_result = Rules.evaluate([9,9,9])
		a.tk_enemy_result = Rules.evaluate([1,2,4])
		a.enemy.hp = 1
		var settled: int = a.enemy.hp
		a._resolve_taikou()
		expect(a.enemy.hp == 0 and settled == 1, "fatal taikou HP settles immediately")
		expect(a.effects.is_empty() and a._global_hitstop == 0.0, "taikou contact FX and hold are deferred")
		a._end_taikou_round()
		a._process(0.479)
		expect(a.last_visuals.player.clip_id != "stance" and a.effects.is_empty(), "fatal action continues after gameplay over before contact")
		a._process(0.002)
		expect(a._global_hitstop > 0.0 and a.effects.size() > 0, "fatal contact emits cues once during over")
		var effect_count: int = a.effects.size()
		a._process(0.1)
		expect(a.effects.size() <= effect_count and a.enemy.hp == 0, "contact hold does not replay gameplay or effects")
		a._process(0.14)
		a._process(0.46)
		expect(a.last_visuals.foe.clip_id == "ko" and is_equal_approx(a.last_visuals.foe.frame,27.0), "fatal KO finishes at down pose")
		a._start_round()
		expect(a.presentation.exchange.is_empty() and a._global_hitstop == 0.0 and a.last_visuals.is_empty(), "reset clears terminal queue/visuals/global hold")
		a.battle_mode = "realtime"
		a.round_phase = "fight"
		a.player.meter = 5.0
		a.hand = ["wave","jab","guard","focus","rush"]
		a._try_play(0)
		for step in range(60):
			a.player.tick(1.0/60.0,0.0,false)
			a._sync_3d_layer()
			if not a.projectiles.is_empty(): break
		expect(a.projectiles.size() == 1 and is_equal_approx(a.last_visuals.player.frame,17.0), "live wave emits once on final active pose")
		for step in range(60):
			a.player.tick(1.0/60.0,0.0,false)
			if a.player.can_act(): break
		a._try_play(1)
		if not a.projectiles.is_empty():
			a.projectiles[0].pos = a.enemy.position + Vector2(0,-150)
			a._tick_projectiles(0.0)
			a._sync_3d_layer()
		expect(a.enemy.hp == 90 and a.projectiles.is_empty(), "live late projectile settles damage once")
		expect(a.last_visuals.player.clip_id == "jab" and a.player.active_card().id == "jab", "late wave collision preserves current jab action")
		a._start_round()
		a.battle_mode = "realtime"
		a.round_phase = "fight"
		a.player.meter = 5.0
		a.hand = ["jab","guard","focus","rush","retreat"]
		a._try_play(0)
		a.enemy.hp = 1
		a.projectiles = [{"pos":a.enemy.position + Vector2(0,-150),"dir":1,"damage":10,"owner_is_player":true,"t":0.0,"round_id":a._round_serial,"action_seq":0}]
		a._tick_projectiles(0.0)
		a._sync_3d_layer()
		expect(a.round_phase == "over" and a.last_visuals.player.clip_id == "jab", "fatal late wave preserves winner current action before freeze")
		a._process(0.08)
		a._process(0.7)
		expect(a.last_visuals.player.clip_id == "stance" and a.last_visuals.foe.frame == 27.0, "fatal late wave finishes current action and KO without further settling")
	for failure in failures: print("FAIL: ", failure)
	print("BATTLE INTEGRATION CHECK: %d/%d passed" % [total - failures.size(),total])
	quit(0 if failures.is_empty() else 1)
