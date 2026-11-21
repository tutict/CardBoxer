extends SceneTree
## Normal automatic match: original spawns, hands, rules and engine tick.
## The observer reads after drawing; it never injects poses or freezes gameplay.
const ArenaScript = preload("res://scripts/arena.gd")
var arena
var directory := ""
var frames := 0
var shot_count := 0
var last_key := ""
var last_hold := false
var rows: Array = []
var contact_only := false
var continuous := false

func _initialize() -> void:
	seed(20261119)
	OS.set_environment("CARD_BOXER_3D", "1")
	OS.set_environment("CARD_BOXER_BATTLE_MODE", "taikou")
	OS.set_environment("CARD_BOXER_TAIKOU_BOT", "1")
	OS.set_environment("CARD_BOXER_CAPTURE", "")
	directory = OS.get_environment("NATIVE_MATCH_OUT")
	contact_only = OS.get_environment("NATIVE_MATCH_CONTACT_ONLY") == "1"
	continuous = OS.get_environment("NATIVE_MATCH_CONTINUOUS") == "1"
	if directory == "":
		print("FAIL: NATIVE_MATCH_OUT is required")
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(directory)
	call_deferred("_run")

func _v2(value: Vector2) -> Array:
	return [value.x, value.y]

func _save(key: String) -> void:
	var image := root.get_texture().get_image()
	var path := directory.path_join("match-%04d-%s.png" % [shot_count, key])
	image.save_png(path)
	var visuals: Dictionary = arena.last_visuals
	var row := {"file":path,"frame":frames,"round":arena.round_index,
		"phase":arena.round_phase,"turn":arena.tk_turn,"taikou":arena.tk_phase,
		"hp":[arena.player.hp,arena.enemy.hp],
		"positions":[_v2(arena.player.position),_v2(arena.enemy.position)],
		"hold":arena._global_hitstop,"exchange_time":arena.presentation.exchange_time,
		"visuals":{}}
	for role in ["player","foe"]:
		var visual: Dictionary = visuals.get(role,{})
		row.visuals[role] = {"clip":visual.get("clip_id",""),"frame":visual.get("frame",0.0),
			"shift":_v2(visual.get("canvas_shift",Vector2.ZERO)),"frozen":visual.get("frozen",false)}
	rows.append(row)
	shot_count += 1
	print("MATCH_CAPTURE ", key, " hp=", arena.player.hp, "/", arena.enemy.hp)

func _run() -> void:
	arena = ArenaScript.new()
	root.add_child(arena)
	while frames < 16000:
		await process_frame
		await RenderingServer.frame_post_draw
		frames += 1
		var hold: bool = arena._global_hitstop > 0.0
		var key := "%d-%d-%s-%s" % [arena.round_index,arena.tk_turn,arena.round_phase,arena.tk_phase]
		var periodic: bool = continuous and arena.round_index == 1 and arena.tk_turn <= 2 \
			and arena.tk_phase == "resolve" and frames % 3 == 0
		if frames == 5 or key != last_key or (hold and not last_hold) or periodic:
			_save(key + ("-contact" if hold and not last_hold else "") + ("-f%05d" % frames if periodic else ""))
		last_key = key
		last_hold = hold
		if contact_only and hold and arena.tk_phase == "resolve":
			break
		if arena.round_phase == "match_over" and frames > 120:
			_save("match-over")
			break
	var file := FileAccess.open(directory.path_join("match.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify({"frames":frames,"shots":shot_count,"phase":arena.round_phase,"rows":rows}))
	file.close()
	print("NORMAL_MATCH_CAPTURE: ", arena.round_phase, " frames=",frames," shots=",shot_count)
	arena.free()
	quit(0 if contact_only or frames < 16000 else 1)
