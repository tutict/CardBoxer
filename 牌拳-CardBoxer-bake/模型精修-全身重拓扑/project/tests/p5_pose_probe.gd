extends SceneTree
## P5 · 引擎内上线态 A/B：同进程三模式（换动作表，不换 mapping）。
##
## 三种模式（同一 Godot 进程，避免跨进程整帧像素等价不成立）：
##   shipped      —— 完全不覆盖，读回的 3D 表就是 P5/R2 落盘表；
##   rolled_back  —— 运行时把 cards 换成 orig/pre-p5 原表，等价 P4 上线态；
##   reapplied    —— 再换回落盘表，验证可逆与同进程渲染可复现。
##
## 帧清单由 data/p5_probe_frames.json 给出：wave/cross 的改动帧 + stance/jab
## 两个「R2 明确不动」的零差对照。全部帧取自独立读回算出的改动帧集合，
## 不拿 P4 的改动帧来凑数（那会全零）。
##
## arena.paused=true 冻结自动同步，动作由探针按场景驱动（静态 A/B，
## 不是真实对局；整帧板上的「暂停」来自探针冻结，不是游戏默认态）。
##
## 跑法：P5_OUT=<abs> P5_ORIG=<abs> P5_FRAMES=<abs json> CARD_BOXER_3D=1 \
##   godot --path . --resolution 1280x720 --quit-after 6000 \
##   --script res://tests/p5_pose_probe.gd

const ArenaScene = preload("res://scenes/main.tscn")


class Driver:
	extends Node

	const WARM := 40
	var arena: Node2D
	var out_dir := ""
	var orig_dir := ""
	var frames_file := ""
	var wait := 0
	var initialized := false
	var busy := false
	var done := false
	var idx := 0
	var rows: Array = []
	var scene_frames: Array = []
	var marker_card := "wave"
	var marker_frame := 17
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


	func _read_json(path: String) -> Dictionary:
		var txt := FileAccess.get_file_as_string(path)
		var parsed: Variant = JSON.parse_string(txt)
		if typeof(parsed) != TYPE_DICTIONARY:
			push_error("P5 probe: cannot parse " + path)
			return {}
		return parsed as Dictionary


	func _load_frames() -> void:
		var cfg := _read_json(frames_file)
		scene_frames = cfg.get("frames", [])
		marker_card = String(cfg.get("marker", {}).get("card", "wave"))
		marker_frame = int(cfg.get("marker", {}).get("frame", 17))


	func _modes() -> Array:
		return ["shipped", "rolled_back", "reapplied"]


	func _scenes() -> Array:
		var out: Array = []
		for m in _modes():
			for f in scene_frames:
				out.append({"mode": String(m),
					"card": String((f as Dictionary).get("card", "")),
					"frame": int((f as Dictionary).get("frame", 0)),
					"role": String((f as Dictionary).get("role", ""))})
		return out


	## wave:17 的 f_hand 在 P5 里被推到最远；两个坐标即可区分两版表。
	func _marker(m: Dictionary) -> String:
		if not m.has("cards"):
			return "<no_cards>"
		var cards: Dictionary = m["cards"]
		if not cards.has(marker_card):
			return "<no_" + marker_card + ">"
		var e: Dictionary = cards[marker_card]
		var tr: Array = e.get("track", [])
		if tr.size() <= marker_frame:
			return "<short_track>"
		var fh: Array = (tr[marker_frame] as Dictionary).get("f_hand", [])
		if fh.size() != 2:
			return "<bad_f_hand>"
		return "%.6f|%.6f" % [float(fh[0]), float(fh[1])]


	func _set_cards(which: String) -> void:
		if which == "rolled_back":
			arena.motion_3d["cards"] = legacy_cards_p
			arena.motion_3d_foe["cards"] = legacy_cards_f
		elif which == "reapplied":
			arena.motion_3d["cards"] = shipped_cards_p
			arena.motion_3d_foe["cards"] = shipped_cards_f
		# shipped 刻意不覆盖


	## 引擎侧实时算 mf：与 rig_driver.gd 的 tf 输入同口径。
	## stance 没有 cards 条目（apply("stance") 是引擎特例），返回 -1。
	func _mf_live(card: String, frame: int) -> float:
		var cards: Dictionary = arena.motion_3d["cards"]
		if not cards.has(card):
			return -1.0
		var tr: Array = (cards[card] as Dictionary).get("track", [])
		if frame < 0 or frame >= tr.size():
			return -1.0
		var fh: Array = (tr[frame] as Dictionary).get("f_hand", [])
		var st: Array = (arena.motion_3d["stance"] as Dictionary).get(
			"f_hand", [])
		if fh.size() != 2 or st.size() != 2:
			return -1.0
		return Vector2(float(fh[0]), float(fh[1])).distance_to(
			Vector2(float(st[0]), float(st[1])))


	func _sv_png(tag: String, layer, key: String) -> String:
		var p := out_dir + "/p5-" + key + "-sv-" + tag + ".png"
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
			"frame": int(s["frame"]), "role": String(s["role"]),
			"key": key,
			"table_marker_player": _marker(arena.motion_3d),
			"table_marker_foe": _marker(arena.motion_3d_foe),
			"cap_live": float(arena.motion_3d["mapping"]["leg_cap_deg"]),
			"mode_live": String(arena.motion_3d["mapping"].get(
				"leg_mode", "<absent>")),
			"mf_live": _mf_live(String(s["card"]), int(s["frame"])),
			"player_sv": _sv_png("player", lp, key),
			"foe_sv": _sv_png("foe", lf, key),
			"live": out_dir + "/p5-" + key + "-live.png",
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
			_load_frames()
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
				"frames_loaded": scene_frames.size(),
				"marker_card": marker_card,
				"marker_frame": marker_frame,
				"shipped_marker_p": shipped_marker_p,
				"shipped_marker_f": shipped_marker_f,
				"legacy_marker_p": legacy_marker_p,
				"legacy_marker_f": legacy_marker_f}
			print("P5_POSE_JSON " + JSON.stringify(payload))
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
	var out_dir := OS.get_environment("P5_OUT")
	var orig_dir := OS.get_environment("P5_ORIG")
	var frames_file := OS.get_environment("P5_FRAMES")
	if out_dir == "" or orig_dir == "" or frames_file == "":
		print("P5_POSE_JSON " + JSON.stringify(
			{"error": "P5_OUT/P5_ORIG/P5_FRAMES missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var inst: Node2D = (ArenaScene as PackedScene).instantiate()
	root.add_child(inst)
	var d := Driver.new()
	d.arena = inst
	d.out_dir = out_dir
	d.orig_dir = orig_dir
	d.frames_file = frames_file
	root.add_child(d)
