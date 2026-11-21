extends SceneTree
## Fixed input through production arena._process / play_card / apply_hit.
## Run the identical harness against baseline and current res:// to compare gameplay.
const ArenaScript = preload("res://scripts/arena.gd")
const Defs = preload("res://scripts/card_data.gd")
const DT := 1.0 / 60.0

class QuietAI:
	extends RefCounted
	var movement := 0.0
	func update(_dt: float, _opponent, _hand: Array) -> Dictionary:
		return {"move": movement, "play": -1}
	func note_played(_id: String) -> void:
		pass

var out_dir: String
var scenarios: Array = []
var failures: Array = []
var event_rows: Array = []
var tick_index := 0
var current_scenario := ""
var captures := false

func _initialize() -> void:
	call_deferred("_run")

func _has_property(object: Object, key: String) -> bool:
	for property in object.get_property_list():
		if String(property.name) == key:
			return true
	return false

func _expect(value: bool, label: String) -> void:
	if not value:
		failures.append(current_scenario + ": " + label)

func _hit(player: bool, damage: int, blocked: bool, dodged: bool) -> void:
	event_rows.append({"tick": tick_index, "kind": "hit", "player_attacker": player,
		"damage": damage, "blocked": blocked, "dodged": dodged})

func _card(id: String, player: bool) -> void:
	event_rows.append({"tick": tick_index, "kind": "card", "id": id, "player": player})

func _super(id: String, player: bool) -> void:
	event_rows.append({"tick": tick_index, "kind": "super", "id": id, "player": player})

func _fighter(f) -> Dictionary:
	return {"hp": f.hp, "meter": snappedf(float(f.meter), 0.000001), "state": int(f.state),
		"phase": f._action_phase, "phase_time": snappedf(float(f._phase_time), 0.000001),
		"state_time": snappedf(float(f.state_time), 0.000001), "card": String(f._action.get("id", "")),
		"position": [snappedf(f.position.x, 0.000001), snappedf(f.position.y, 0.000001)],
		"facing": f.facing, "local_hitstop": snappedf(float(f._hitstop), 0.000001),
		"combo": f.combo_name(), "combo_bonus": f.combo_bonus(), "super": f._is_super,
		"guarding": f.is_guarding(), "dodging": f.is_invulnerable(), "visual_only": f._visual_only}

func _gameplay(a) -> Dictionary:
	var projectiles: Array = []
	for p in a.projectiles:
		projectiles.append({"position": [snappedf(p.pos.x, 0.000001), snappedf(p.pos.y, 0.000001)],
			"damage": p.damage, "player": p.owner_is_player, "t": snappedf(float(p.t), 0.000001)})
	return {"tick": tick_index, "player": _fighter(a.player), "foe": _fighter(a.enemy),
		"round_phase": a.round_phase, "round_wins": a.round_wins.duplicate(), "tk_phase": a.tk_phase,
		"tk_turn": a.tk_turn, "tk_winner": a.tk_winner, "tk_damage": a.tk_damage,
		"tk_rage": [a.tk_player_rage, a.tk_enemy_rage], "tk_ex": [a.tk_player_ex, a.tk_enemy_ex],
		"reveal": [a.tk_player_reveal.duplicate(), a.tk_enemy_reveal.duplicate()],
		"hand": a.hand.duplicate(), "enemy_hand": a.enemy_hand.duplicate(),
		"cooldowns": a.cooldowns.duplicate(), "enemy_cooldowns": a.enemy_cooldowns.duplicate(),
		"round_time": snappedf(float(a.round_time_left), 0.000001),
		"global_hitstop": snappedf(float(a._global_hitstop), 0.000001),
		"combo_count": a.combo_count, "projectiles": projectiles}

func _visuals(a) -> Dictionary:
	if _has_property(a, "last_visuals"):
		return a.last_visuals.duplicate(true)
	return {"unavailable": "baseline has no NativeMotion presentation"}

func _capture(a, name: String, frame: int) -> Dictionary:
	var result: Dictionary = {}
	var prefix := out_dir + "/" + name + "-f%04d" % frame
	for role in ["player", "foe"]:
		var layer = a.layer_3d if role == "player" else a.layer_3d_foe
		if layer != null and layer.sv != null:
			var image: Image = layer.sv.get_texture().get_image()
			var path: String = prefix + "-" + String(role) + ".png"
			result[role] = {"path": path, "png_error": image.save_png(path)}
	if frame % 6 == 0:
		var live: Image = root.get_texture().get_image()
		result["live"] = {"path": prefix + "-live.png", "png_error": live.save_png(prefix + "-live.png")}
	return result

func _new_arena(config: Dictionary):
	seed(20261119)
	var a = ArenaScript.new()
	a.battle_mode = config.get("mode", "realtime")
	root.add_child(a)
	a.set_process(false)
	a.set_physics_process(false)
	a.round_phase = "fight"
	a.phase_time = 0.0
	a.tk_bot = false
	a._capture_dir = ""
	a.ai = QuietAI.new()
	a.demo_ai = null
	a._deck = ["jab", "cross", "uppercut", "sweep", "wave", "throw", "rush", "backstep", "guard", "sidestep", "focus", "recover"]
	a._enemy_deck = a._deck.duplicate()
	var distance: float = float(config.get("distance", 85.0))
	var swapped: bool = bool(config.get("swapped", false))
	a.player.reset_for_round(640.0 + distance * 0.5 if swapped else 640.0 - distance * 0.5, -1 if swapped else 1)
	a.enemy.reset_for_round(640.0 - distance * 0.5 if swapped else 640.0 + distance * 0.5, 1 if swapped else -1)
	a.player.meter = 5.0
	a.enemy.meter = 5.0
	a.hand = config.get("hand", ["jab", "uppercut", "wave", "cross", "guard"]).duplicate()
	a.enemy_hand = config.get("enemy_hand", ["jab", "uppercut", "wave", "cross", "guard"]).duplicate()
	a.cooldowns = [0.0, 0.0, 0.0, 0.0, 0.0]
	a.enemy_cooldowns = a.cooldowns.duplicate()
	if bool(config.get("fatal", false)):
		if config.get("actor", "player") == "player":
			a.enemy.hp = 1
		else:
			a.player.hp = 1
	if bool(config.get("ex", false)):
		a.tk_player_rage = 100.0
		a.tk_enemy_rage = 100.0
	for f in [a.player, a.enemy]:
		f.hit_confirmed.connect(_hit)
		f.card_played.connect(_card)
		f.super_confirmed.connect(_super)
	return a

func _input(a, config: Dictionary, sequence_index: int) -> bool:
	var actor = a.player if config.get("actor", "player") == "player" else a.enemy
	var sequence: Array = config.get("sequence", ["jab"])
	if sequence_index >= sequence.size() or not actor.can_act():
		return false
	var id: String = sequence[sequence_index]
	var hand: Array = a.hand if actor == a.player else a.enemy_hand
	var slot := hand.find(id)
	if slot < 0:
		_expect(false, "fixed input card missing " + id)
		return false
	if actor == a.player:
		a._try_play(slot)
	else:
		a._try_enemy_play(slot)
	return String(actor._action.get("id", "")) == id and not actor.can_act()

func _scenario(config: Dictionary) -> void:
	current_scenario = String(config.name)
	event_rows = []
	tick_index = 0
	var motion_source_sha256 := FileAccess.get_sha256("res://data/combat_motion_3d.json") if FileAccess.file_exists("res://data/combat_motion_3d.json") else ""
	var source_sha256: Dictionary = {}
	for source in ["data/combat_motion_3d.json", "scripts/native_motion.gd", "scripts/rig_driver.gd",
		"scripts/fighter_3d_layer.gd", "scripts/battle_presentation.gd", "scripts/arena.gd", "scripts/fighter.gd",
		"assets/3d/player-rigged.glb", "assets/3d/foe-rigged.glb"]:
		if FileAccess.file_exists("res://" + String(source)):
			source_sha256[source] = FileAccess.get_sha256("res://" + String(source))
	var a = _new_arena(config)
	await process_frame
	var traces: Array = []
	var images: Array = []
	var visual_rows: Array = []
	var sequence_index := 0
	var fatal_reached := false
	var hp_at_reveal: Array = []
	if a.battle_mode == "taikou":
		# Production discard, select and reveal inputs; supplied hands are immutable setup.
		a._taikou_confirm()
		for i in [0, 1, 2]:
			a._taikou_toggle(i)
		a._taikou_confirm()
		hp_at_reveal = [a.player.hp, a.enemy.hp]
	var max_ticks: int = int(config.get("ticks", 150))
	var capture_stride := maxi(1, int(OS.get_environment("NATIVE_LIVE_STRIDE")))
	for frame in range(max_ticks):
		tick_index = frame
		if a.battle_mode == "realtime":
			if not fatal_reached and _input(a, config, sequence_index):
				sequence_index += 1
			if frame == int(config.get("defender_tick", -1)):
				var defender = a.enemy if config.get("actor", "player") == "player" else a.player
				defender.play_card(String(config.get("defender_card", "guard")))
		if a.round_phase == "fight":
			a._process(DT)
		else:
			fatal_reached = true
			# The production terminal branch stops fighter/projectile physics while
			# allowing visual hitstop and terminal presentation clocks to finish.
			a._process(DT)
		traces.append(_gameplay(a))
		var visual_row := {"tick": frame, "visuals": _visuals(a), "round_phase": a.round_phase}
		if a.player.has_method("presentation_snapshot"):
			visual_row["snapshots"] = {"player": a.player.presentation_snapshot(), "foe": a.enemy.presentation_snapshot()}
			visual_row["context"] = a._presentation_context()
		visual_rows.append(visual_row)
		if captures and frame % capture_stride == 0:
			await process_frame
			await RenderingServer.frame_post_draw
			images.append({"tick": frame, "capture": _capture(a, current_scenario, frame)})
		if a.battle_mode == "taikou" and a.tk_phase == "reveal":
			_expect([a.player.hp, a.enemy.hp] == hp_at_reveal, "reveal must not apply damage")
	var hits: Array = event_rows.filter(func(e): return e.kind == "hit")
	if config.get("expect", "") == "block":
		_expect(hits.any(func(e): return e.blocked), "actual block event required")
	if config.get("expect", "") == "dodge":
		_expect(hits.any(func(e): return e.dodged), "actual dodge event required")
	if config.get("expect", "") == "combo":
		_expect(traces.any(func(t): return t.player.combo != "" or t.foe.combo != ""), "actual combo required")
	if config.get("expect", "") == "super":
		_expect(traces.any(func(t): return t.player.super or t.foe.super), "actual super action required")
		_expect(hits.any(func(e): return e.damage >= 20), "actual super bonus damage required")
	if config.get("expect", "") == "melee_super":
		_expect(event_rows.any(func(e): return e.kind == "super"), "actual melee super confirmed event required")
	if config.has("winner"):
		_expect(a.tk_winner == config.winner, "taikou winner " + str(config.winner) + " actual " + a.tk_winner)
	if bool(config.get("fatal", false)):
		_expect(fatal_reached, "fatal strike must end round")
		var over_rows: Array = traces.filter(func(t): return t.round_phase in ["over", "match_over"])
		if over_rows.size() > 1:
			for role in ["player", "foe"]:
				_expect(over_rows[0][role].position == over_rows[-1][role].position,
					"terminal branch stops fighter movement " + role)
		if bool(a.use_3d) and _has_property(a, "last_visuals") and not a.last_visuals.is_empty():
			var victim: String = "foe" if config.get("actor", "player") == "player" else "player"
			_expect(a.last_visuals.get(victim, {}).get("clip_id", "") == "ko", "fatal target shows native KO")
			_expect(float(a.last_visuals.get(victim, {}).get("frame", -1)) >= 26.99, "native terminal KO reaches final authored frame")
		var before: Dictionary = _gameplay(a)
		a._start_round()
		_expect(a.player.hp == 100 and a.enemy.hp == 100, "reset restores HP")
		_expect(a.projectiles.is_empty(), "reset clears projectiles")
		if _has_property(a, "last_visuals"):
			a._sync_3d_layer()
			for role in ["player", "foe"]:
				_expect(a.last_visuals.get(role, {}).get("clip_id", "") != "ko", "reset clears stale KO " + role)
			visual_rows.append({"tick": max_ticks, "visuals": _visuals(a), "reset": true, "before": before})
			if captures:
				await process_frame
				await RenderingServer.frame_post_draw
				images.append({"tick": max_ticks, "capture": _capture(a, current_scenario, max_ticks), "reset": true})
	var result := {"config": config, "gameplay": traces, "events": event_rows.duplicate(true),
		"visuals": visual_rows, "images": images, "use_3d": a.use_3d, "rendered": captures,
		"motion_source_sha256": motion_source_sha256, "source_sha256": source_sha256}
	scenarios.append(result)
	var file := FileAccess.open(out_dir + "/" + current_scenario + ".json", FileAccess.WRITE)
	file.store_string(JSON.stringify(result))
	file.close()
	a.free()
	print("NATIVE_LIVE_SCENARIO " + current_scenario + " hits=" + str(hits.size()))

func _configs() -> Array:
	var configs: Array = []
	for role in ["player", "foe"]:
		var actor: String = "player" if role == "player" else "foe"
		for card in Defs.CARDS.keys():
			configs.append({"name": actor + "-card-" + String(card), "actor": actor,
				"sequence": [card], "hand": [card, "jab", "uppercut", "wave", "guard"],
				"enemy_hand": [card, "jab", "uppercut", "wave", "guard"]})
		configs.append({"name": actor + "-block", "actor": actor, "sequence": ["jab"], "defender_tick": 0,
			"defender_card": "guard", "expect": "block"})
		configs.append({"name": actor + "-dodge", "actor": actor, "sequence": ["jab"], "defender_tick": 5,
			"defender_card": "sidestep", "expect": "dodge"})
		configs.append({"name": actor + "-combo-super", "actor": actor, "sequence": ["jab", "uppercut", "wave"],
			"expect": "super", "ticks": 210})
		configs.append({"name": actor + "-melee-super", "actor": actor, "sequence": ["rush", "throw", "uppercut"],
			"hand": ["rush", "throw", "uppercut", "jab", "guard"],
			"enemy_hand": ["rush", "throw", "uppercut", "jab", "guard"], "distance": 255.0,
			"expect": "melee_super", "ticks": 210})
		configs.append({"name": actor + "-wave-new-action", "actor": actor, "sequence": ["wave", "jab", "jab", "jab"],
			"hand": ["wave", "jab", "jab", "jab", "jab"], "enemy_hand": ["wave", "jab", "jab", "jab", "jab"],
			"distance": 700, "ticks": 180})
		configs.append({"name": actor + "-late-wave-fatal", "actor": actor, "sequence": ["wave", "jab", "jab", "jab"],
			"hand": ["wave", "jab", "jab", "jab", "jab"], "enemy_hand": ["wave", "jab", "jab", "jab", "jab"],
			"distance": 700, "fatal": true, "ticks": 140})
		configs.append({"name": actor + "-fatal-facing-reset", "actor": actor, "sequence": ["jab"],
			"swapped": true, "fatal": true, "ticks": 80})
	var strong: Array = ["jab", "jab", "jab", "jab", "jab"]
	var weak: Array = ["cross", "sweep", "throw", "cross", "sweep"]
	for winner in ["player", "enemy", "draw"]:
		configs.append({"name": "taikou-" + String(winner), "mode": "taikou", "winner": winner,
			"hand": weak if winner == "enemy" else strong, "enemy_hand": weak if winner == "player" else strong,
			"ticks": 170})
	configs.append({"name": "taikou-ex-fatal", "mode": "taikou", "hand": strong, "enemy_hand": weak,
		"ex": true, "fatal": true, "ticks": 170})
	return configs

func _run() -> void:
	out_dir = OS.get_environment("NATIVE_LIVE_OUT")
	if out_dir.is_empty():
		out_dir = ProjectSettings.globalize_path("res://../reports/live")
	DirAccess.make_dir_recursive_absolute(out_dir)
	captures = OS.get_environment("NATIVE_LIVE_CAPTURE") == "1"
	if captures and DisplayServer.get_name() == "headless":
		push_error("Live image evidence requires real renderer")
		quit(2)
		return
	var only := OS.get_environment("NATIVE_LIVE_SCENARIOS")
	for config in _configs():
		if only.is_empty() or Array(only.split(",")).has(config.name):
			await _scenario(config)
	_expect(not scenarios.is_empty(), "at least one scenario must execute")
	var payload := {"failures": failures, "scenario_count": scenarios.size(),
		"source_project": ProjectSettings.globalize_path("res://"), "fixed_dt": DT,
		"rendered": captures, "evidence": "Production state machine, fixed input, no direct sampled-pose injection"}
	var file := FileAccess.open(out_dir + "/summary.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(payload, "\t"))
	file.close()
	print("NATIVE_LIVE_RESULT " + JSON.stringify(payload))
	quit(0 if failures.is_empty() else 1)
