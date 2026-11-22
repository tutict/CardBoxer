extends SceneTree
## P3 上线态引擎内取证：读回落盘 leg_mode / leg_cap_deg，做同进程 A/B。
##
## 四种模式（同一 Godot 进程，避免跨进程整帧像素等价不成立）：
##   shipped      —— 完全不覆盖 mapping，读回的就是落盘 atan / 12.0；
##   rolled_back  —— 运行时改回 hard / 9.0，等价于 P2 上线态；
##   reapplied    —— 再设回落盘值，验证可逆与渲染可复现；
##   legacy_compat—— 删掉 leg_mode 键并把 cap 设 9.0，验证「旧动作表
##                    配新驱动」回落 hard，行为与 rolled_back 逐像素相同。
##
## arena.paused=true 冻结自动同步，动作由探针按场景驱动（静态 A/B，
## 不是真实对局；真实对局取证在 live-match/，那里没有「暂停」字样）。
##
## 跑法：P3_OUT=<abs> CARD_BOXER_3D=1 godot --path . \
##   --resolution 1280x720 --quit-after 6000 \
##   --script res://tests/p3_plateau_probe.gd

const ArenaScene = preload("res://scenes/main.tscn")


class Driver:
	extends Node

	const WARM := 40
	var arena: Node2D
	var out_dir := ""
	var wait := 0
	var initialized := false
	var busy := false
	var done := false
	var idx := 0
	var rows: Array = []
	var shipped_cap_player := -1.0
	var shipped_cap_foe := -1.0
	var shipped_mode_player := ""
	var shipped_mode_foe := ""


	func _frames() -> Array:
		var out: Array = [
			{"card": "stance", "frame": 0},
			{"card": "jab", "frame": 1},
			{"card": "sweep", "frame": 7},
			{"card": "hit_heavy", "frame": 1}]
		# sweep 14..21 是实测最长的 clamp 削平段（14..26，13 帧全 -9°）
		for i in range(14, 22):
			out.append({"card": "sweep", "frame": i})
		return out


	func _modes() -> Array:
		return ["shipped", "rolled_back", "reapplied", "legacy_compat"]


	func _scenes() -> Array:
		var out: Array = []
		for m in _modes():
			for s in _frames():
				out.append({"mode": String(m), "card": String(s["card"]),
					"frame": int(s["frame"])})
		return out


	func _set_mode(mode: String, cap: float) -> void:
		arena.motion_3d["mapping"]["leg_mode"] = mode
		arena.motion_3d["mapping"]["leg_cap_deg"] = cap
		arena.motion_3d_foe["mapping"]["leg_mode"] = mode
		arena.motion_3d_foe["mapping"]["leg_cap_deg"] = cap


	func _clear_mode(cap: float) -> void:
		arena.motion_3d["mapping"].erase("leg_mode")
		arena.motion_3d["mapping"]["leg_cap_deg"] = cap
		arena.motion_3d_foe["mapping"].erase("leg_mode")
		arena.motion_3d_foe["mapping"]["leg_cap_deg"] = cap


	func _mode_of(m: Dictionary) -> String:
		return String(m.get("leg_mode", "<absent>"))


	func _sv_png(tag: String, layer, key: String) -> String:
		var p := out_dir + "/p3-" + key + "-sv-" + tag + ".png"
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
			"mode_live_player": _mode_of(arena.motion_3d["mapping"]),
			"mode_live_foe": _mode_of(arena.motion_3d_foe["mapping"]),
			"cap_live_player": float(arena.motion_3d["mapping"]["leg_cap_deg"]),
			"cap_live_foe": float(arena.motion_3d_foe["mapping"]["leg_cap_deg"]),
			"player_sv": _sv_png("player", lp, key),
			"foe_sv": _sv_png("foe", lf, key),
			"live": out_dir + "/p3-" + key + "-live.png",
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
			# 必须在任何覆盖之前读回落盘真值
			shipped_cap_player = float(
				arena.motion_3d["mapping"]["leg_cap_deg"])
			shipped_cap_foe = float(
				arena.motion_3d_foe["mapping"]["leg_cap_deg"])
			shipped_mode_player = _mode_of(arena.motion_3d["mapping"])
			shipped_mode_foe = _mode_of(arena.motion_3d_foe["mapping"])
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
				"mapping_cap_player": shipped_cap_player,
				"mapping_cap_foe": shipped_cap_foe,
				"mapping_mode_player": shipped_mode_player,
				"mapping_mode_foe": shipped_mode_foe}
			print("P3_PLATEAU_JSON " + JSON.stringify(payload))
			get_tree().quit(0)
			return
		var s: Dictionary = scenes[idx]
		var mode := String(s["mode"])
		if mode == "rolled_back":
			_set_mode("hard", 9.0)
		elif mode == "reapplied":
			_set_mode(shipped_mode_player, shipped_cap_player)
		elif mode == "legacy_compat":
			_clear_mode(9.0)
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
	var out_dir := OS.get_environment("P3_OUT")
	if out_dir == "":
		print("P3_PLATEAU_JSON " + JSON.stringify(
			{"error": "P3_OUT missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var inst: Node2D = (ArenaScene as PackedScene).instantiate()
	root.add_child(inst)
	var d := Driver.new()
	d.arena = inst
	d.out_dir = out_dir
	root.add_child(d)
