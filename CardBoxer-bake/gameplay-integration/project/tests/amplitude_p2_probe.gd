extends SceneTree
## P2 腿部幅度 · 引擎内 A/B 探针（单进程，运行时切 leg_cap_deg）。
##
## 只改 arena.motion_3d / motion_3d_foe 里的 mapping 字典（rig_driver.gd
## 的 mapping 是同一 Dictionary 引用），再直接 apply(card, frame) 出图；
## 不写任何磁盘源文件、不碰 HP / 判定 / 阶段时长 / GLB。
## arena.paused=true 让 _process 不再自动同步，全部由本探针按场景驱动。
##
## 跑法：AMPLITUDE_P2_OUT=<abs> CARD_BOXER_3D=1 godot --path . \
##   --resolution 1280x720 --quit-after 3000 \
##   --script res://tests/amplitude_p2_probe.gd

const ArenaScene = preload("res://scenes/main.tscn")


class Driver:
	extends Node

	const WARM := 60
	const CAPS := [3.0, 6.0, 9.0, 12.0]
	var arena: Node2D
	var out_dir := ""
	var wait := 0
	var initialized := false
	var busy := false
	var done := false
	var idx := 0
	var rows: Array = []


	func _scenes() -> Array:
		var out: Array = []
		for cap in CAPS:
			for s in [{"card": "stance", "frame": 0},
					{"card": "jab", "frame": 1},
					{"card": "sweep", "frame": 7},
					{"card": "hit_heavy", "frame": 1}]:
				out.append({"cap": cap, "card": s["card"],
					"frame": s["frame"]})
		return out


	func _set_cap(cap: float) -> void:
		arena.motion_3d["mapping"]["leg_cap_deg"] = cap
		arena.motion_3d_foe["mapping"]["leg_cap_deg"] = cap


	func _sv_png(tag: String, layer, key: String) -> String:
		var p := out_dir + "/ap2-" + key + "-sv-" + tag + ".png"
		if layer != null and layer.sv != null:
			var t = layer.sv.get_texture()
			if t != null:
				var im = t.get_image()
				if im != null:
					im.save_png(p)
		return p


	func _capture(s: Dictionary) -> Dictionary:
		var cap := float(s["cap"])
		var key := "cap%02d-%s%02d" % [int(cap), String(s["card"]),
			int(s["frame"])]
		var lp = arena.layer_3d
		var lf = arena.layer_3d_foe
		var rec := {
			"cap": cap, "card": String(s["card"]),
			"frame": int(s["frame"]), "key": key,
			"player_sv": _sv_png("player", lp, key),
			"foe_sv": _sv_png("foe", lf, key),
			"live": out_dir + "/ap2-" + key + "-live.png",
		}
		if lp != null:
			rec["player_delta"] = lp.drv.last_delta_deg.duplicate()
		if lf != null:
			rec["foe_delta"] = lf.drv.last_delta_deg.duplicate()
		return rec


	func _process(_d: float) -> void:
		if done or busy:
			return
		if not initialized:
			initialized = true
			arena.paused = true
		wait += 1
		if wait < WARM:
			return
		busy = true
		var scenes := _scenes()
		if idx >= scenes.size():
			done = true
			var payload := {"rows": rows,
				"use_3d": bool(arena.use_3d),
				"env_3d": OS.get_environment("CARD_BOXER_3D"),
				"hp": [int(arena.player.hp), int(arena.enemy.hp)],
				"cards_player": int(arena.motion_3d["cards"].size()),
				"cards_foe": int(arena.motion_3d_foe["cards"].size())}
			print("AMPLITUDE_P2_JSON " + JSON.stringify(payload))
			get_tree().quit(0)
			return
		var s: Dictionary = scenes[idx]
		_set_cap(float(s["cap"]))
		if arena.layer_3d != null:
			arena.layer_3d.apply(String(s["card"]), int(s["frame"]))
		if arena.layer_3d_foe != null:
			arena.layer_3d_foe.apply(String(s["card"]), int(s["frame"]))
		await RenderingServer.frame_post_draw
		var im := get_viewport().get_texture().get_image()
		var rec := _capture(s)
		rec["live_error"] = int(im.save_png(String(rec["live"])))
		rows.append(rec)
		idx += 1
		wait = WARM - 2
		busy = false


func _init() -> void:
	var out_dir := OS.get_environment("AMPLITUDE_P2_OUT")
	if out_dir == "":
		print("AMPLITUDE_P2_JSON " + JSON.stringify(
			{"error": "AMPLITUDE_P2_OUT missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var inst: Node2D = (ArenaScene as PackedScene).instantiate()
	root.add_child(inst)
	var d := Driver.new()
	d.arena = inst
	d.out_dir = out_dir
	root.add_child(d)
