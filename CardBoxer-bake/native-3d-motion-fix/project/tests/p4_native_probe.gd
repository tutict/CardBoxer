extends SceneTree
## P4 上线态引擎内取证：同进程三模式 A/B（换动作表，不换 mapping）。
##
## 三种模式（同一 Godot 进程，避免跨进程整帧像素等价不成立）：
##   shipped      —— 完全不覆盖，读回的 3D 表就是 micro2 落盘表；
##   rolled_back  —— 运行时把 cards 换成 orig/pre-p4 的原始表，等价 P3 上线态；
##   reapplied    —— 再换回落盘表，验证可逆与同进程渲染可复现。
##
## 代表帧全部选自 landing_tracks.json 的改动帧；P3 用过的 jab1/sweep7/
## hit_heavy1 恰好不在 micro2 的 80 帧里，拿它们做 A/B 会全零。
##
## arena.paused=true 冻结自动同步，动作由探针按场景驱动（静态 A/B，
## 不是真实对局；整帧板上的「暂停」来自探针冻结，不是游戏默认态）。
##
## 跑法：P4_OUT=<abs> P4_ORIG=<abs> CARD_BOXER_3D=1 godot --path . \
##   --resolution 1280x720 --quit-after 6000 \
##   --script res://tests/p4_native_probe.gd

const ArenaScene = preload("res://scenes/main.tscn")


class Driver:
	extends Node

	const WARM := 40
	var arena: Node2D
	var out_dir := ""
	var orig_dir := ""
	var wait := 0
	var initialized := false
	var busy := false
	var done := false
	var idx := 0
	var rows: Array = []
	var shipped_cards_p: Dictionary = {}
	var shipped_cards_f: Dictionary = {}
	var legacy_cards_p: Dictionary = {}
	var legacy_cards_f: Dictionary = {}
	var shipped_cap := -1.0
	var shipped_mode := ""
	var shipped_marker_p := ""
	var shipped_marker_f := ""
	var legacy_marker_p := ""
	var legacy_marker_f := ""


	func _frames() -> Array:
		var out: Array = [
			{"card": "stance", "frame": 0},
			{"card": "jab", "frame": 6},
			{"card": "sweep", "frame": 14},
			{"card": "hit_heavy", "frame": 8}]
		for i in range(6, 12):
			out.append({"card": "focus", "frame": i})
		for i in range(29, 31):
			out.append({"card": "wave", "frame": i})
		return out


	func _modes() -> Array:
		return ["shipped", "rolled_back", "reapplied"]


	func _scenes() -> Array:
		var out: Array = []
		for m in _modes():
			for s in _frames():
				out.append({"mode": String(m), "card": String(s["card"]),
					"frame": int(s["frame"])})
		return out


	func _read_json(path: String) -> Dictionary:
		var txt := FileAccess.get_file_as_string(path)
		var parsed: Variant = JSON.parse_string(txt)
		if typeof(parsed) != TYPE_DICTIONARY:
			push_error("P4 probe: cannot parse " + path)
			return {}
		return parsed as Dictionary


	## focus:8 的 f_knee 落在 micro2 改动段内，用它的两个坐标区分两版表。
	func _marker(m: Dictionary) -> String:
		if not m.has("cards"):
			return "<no_cards>"
		var cards: Dictionary = m["cards"]
		if not cards.has("focus"):
			return "<no_focus>"
		var tr: Array = cards["focus"]["track"]
		if tr.size() <= 8:
			return "<short_track>"
		var kn: Array = tr[8]["f_knee"]
		return "%.6f|%.6f" % [float(kn[0]), float(kn[1])]


	func _set_cards(which: String) -> void:
		if which == "rolled_back":
			arena.motion_3d["cards"] = legacy_cards_p
			arena.motion_3d_foe["cards"] = legacy_cards_f
		elif which == "reapplied":
			arena.motion_3d["cards"] = shipped_cards_p
			arena.motion_3d_foe["cards"] = shipped_cards_f
		# shipped 刻意不覆盖


	func _sv_png(tag: String, layer, key: String) -> String:
		var p := out_dir + "/p4-" + key + "-sv-" + tag + ".png"
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
			"table_marker_player": _marker(arena.motion_3d),
			"table_marker_foe": _marker(arena.motion_3d_foe),
			"cap_live": float(arena.motion_3d["mapping"]["leg_cap_deg"]),
			"mode_live": String(arena.motion_3d["mapping"].get(
				"leg_mode", "<absent>")),
			"player_sv": _sv_png("player", lp, key),
			"foe_sv": _sv_png("foe", lf, key),
			"live": out_dir + "/p4-" + key + "-live.png",
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
			shipped_cap = float(
				arena.motion_3d["mapping"]["leg_cap_deg"])
			shipped_mode = String(arena.motion_3d["mapping"].get(
				"leg_mode", "<absent>"))
			shipped_cards_p = (arena.motion_3d["cards"] as Dictionary).duplicate(true)
			shipped_cards_f = (arena.motion_3d_foe["cards"] as Dictionary).duplicate(true)
			shipped_marker_p = _marker(arena.motion_3d)
			shipped_marker_f = _marker(arena.motion_3d_foe)
			var lp := _read_json(orig_dir + "/motion_input.json")
			var lf := _read_json(orig_dir + "/motion_input_foe.json")
			legacy_cards_p = lp.get("cards", {})
			legacy_cards_f = lf.get("cards", {})
			legacy_marker_p = _marker(lp)
			legacy_marker_f = _marker(lf)
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
				"mapping_cap": shipped_cap,
				"mapping_mode": shipped_mode,
				"shipped_marker_p": shipped_marker_p,
				"shipped_marker_f": shipped_marker_f,
				"legacy_marker_p": legacy_marker_p,
				"legacy_marker_f": legacy_marker_f}
			print("P4_NATIVE_JSON " + JSON.stringify(payload))
			get_tree().quit(0)
			return
		var s: Dictionary = scenes[idx]
		_set_cards(String(s["mode"]))
		if arena.layer_3d != null:
			arena.layer_3d.apply(String(s["card"]), int(s["frame"]))
		if arena.layer_3d_foe != null:
			arena.layer_3d_foe.apply(String(s["card"]), int(s["frame"]))
		await RenderingServer.frame_post_draw
		var key := "%s-%s%02d" % [String(s["mode"]), String(s["card"]),
			int(s["frame"])]
		var im := get_viewport().get_texture().get_image()
		var rec := _capture(s, key)
		rec["live_error"] = int(im.save_png(String(rec["live"])))
		rows.append(rec)
		idx += 1
		wait = WARM - 2
		busy = false


func _init() -> void:
	var out_dir := OS.get_environment("P4_OUT")
	var orig_dir := OS.get_environment("P4_ORIG")
	if out_dir == "" or orig_dir == "":
		print("P4_NATIVE_JSON " + JSON.stringify(
			{"error": "P4_OUT/P4_ORIG missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var inst: Node2D = (ArenaScene as PackedScene).instantiate()
	root.add_child(inst)
	var d := Driver.new()
	d.arena = inst
	d.out_dir = out_dir
	d.orig_dir = orig_dir
	root.add_child(d)
