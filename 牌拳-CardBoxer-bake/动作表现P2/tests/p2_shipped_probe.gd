extends SceneTree
## P2 上线态引擎内取证：不碰落盘值，读回 mapping 并做同进程 A/B。
##
## 三种模式逐个出图：
##   shipped     —— 完全不覆盖 mapping，读回的就是落盘值；
##   rolled_back —— 运行时把 cap 改回 3.0，等价于上线前；
##   reapplied   —— 运行时把 cap 设回「读回的落盘值」，验证可逆与可复现。
## 全部在**同一个 Godot 进程**内完成，避免跨进程整帧像素等价不成立。
## arena.paused=true 冻结自动同步，动作由本探针按场景驱动。
##
## 跑法：P2_SHIPPED_OUT=<abs> CARD_BOXER_3D=1 godot --path . \
##   --resolution 1280x720 --quit-after 3000 \
##   --script res://tests/p2_shipped_probe.gd

const ArenaScene = preload("res://scenes/main.tscn")


class Driver:
	extends Node

	const WARM := 60
	const BASE_CAP := 3.0
	var arena: Node2D
	var out_dir := ""
	var wait := 0
	var initialized := false
	var busy := false
	var done := false
	var idx := 0
	var rows: Array = []
	var mapping_cap_player := -1.0
	var mapping_cap_foe := -1.0


	func _frames() -> Array:
		return [{"card": "stance", "frame": 0},
				{"card": "jab", "frame": 1},
				{"card": "sweep", "frame": 7},
				{"card": "hit_heavy", "frame": 1}]


	func _modes() -> Array:
		return ["shipped", "rolled_back", "reapplied"]


	func _scenes() -> Array:
		var out: Array = []
		for m in _modes():
			for s in _frames():
				out.append({"mode": String(m), "card": String(s["card"]),
					"frame": int(s["frame"])})
		return out


	func _set_cap(cap: float) -> void:
		arena.motion_3d["mapping"]["leg_cap_deg"] = cap
		arena.motion_3d_foe["mapping"]["leg_cap_deg"] = cap


	func _sv_png(tag: String, layer, key: String) -> String:
		var p := out_dir + "/p2s-" + key + "-sv-" + tag + ".png"
		if layer != null and layer.sv != null:
			var t = layer.sv.get_texture()
			if t != null:
				var im = t.get_image()
				if im != null:
					im.save_png(p)
		return p


	func _capture(s: Dictionary, key: String) -> Dictionary:
		var lp = arena.layer_3d
		var lf = arena.layer_3d_foe
		var rec := {
			"mode": String(s["mode"]), "card": String(s["card"]),
			"frame": int(s["frame"]), "key": key,
			"cap_live_player": float(arena.motion_3d["mapping"]["leg_cap_deg"]),
			"cap_live_foe": float(arena.motion_3d_foe["mapping"]["leg_cap_deg"]),
			"player_sv": _sv_png("player", lp, key),
			"foe_sv": _sv_png("foe", lf, key),
			"live": out_dir + "/p2s-" + key + "-live.png",
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
			# 必须在任何 _set_cap 之前读回落盘真值
			mapping_cap_player = float(arena.motion_3d["mapping"]["leg_cap_deg"])
			mapping_cap_foe = float(arena.motion_3d_foe["mapping"]["leg_cap_deg"])
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
				"cards_foe": int(arena.motion_3d_foe["cards"].size()),
				"mapping_cap_player": mapping_cap_player,
				"mapping_cap_foe": mapping_cap_foe}
			print("P2_SHIPPED_JSON " + JSON.stringify(payload))
			get_tree().quit(0)
			return
		var s: Dictionary = scenes[idx]
		var mode := String(s["mode"])
		if mode == "rolled_back":
			_set_cap(BASE_CAP)
		elif mode == "reapplied":
			_set_cap(mapping_cap_player)
		# shipped 模式刻意不覆盖 mapping
		if arena.layer_3d != null:
			arena.layer_3d.apply(String(s["card"]), int(s["frame"]))
		if arena.layer_3d_foe != null:
			arena.layer_3d_foe.apply(String(s["card"]), int(s["frame"]))
		await RenderingServer.frame_post_draw
		var key := "%s-%s%02d" % [mode, String(s["card"]),
			int(s["frame"])]
		var im := get_viewport().get_texture().get_image()
		var rec := _capture(s, key)
		rec["live_error"] = int(im.save_png(String(rec["live"])))
		rows.append(rec)
		idx += 1
		wait = WARM - 2
		busy = false


func _init() -> void:
	var out_dir := OS.get_environment("P2_SHIPPED_OUT")
	if out_dir == "":
		print("P2_SHIPPED_JSON " + JSON.stringify(
			{"error": "P2_SHIPPED_OUT missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var inst: Node2D = (ArenaScene as PackedScene).instantiate()
	root.add_child(inst)
	var d := Driver.new()
	d.arena = inst
	d.out_dir = out_dir
	root.add_child(d)
