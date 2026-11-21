extends SceneTree
## P1 动作覆盖 · 引擎内状态注入探针（单进程跑 6 个场景）。
##
##   stance / reveal / player_win / enemy_win / draw / legacy_player_win
##
## 只写 arena 的表现层状态字段，再显式调 _sync_3d_layer()；不碰 HP /
## 伤害 / 牌型 / 阶段时长 / 判定，也不写任何磁盘源文件。paused=true
## 让 arena._process() 不再自动同步，全部由本探针按场景驱动。
##
## legacy_player_win 是 A/B：运行时把两份动作表裁回 P1 之前的 3 卡，
## 用与 player_win 完全相同的状态再跑一次，用来证明赢家攻击侧零回归。
##
## 跑法：MOTION_P1_OUT=<abs> CARD_BOXER_3D=1 godot --path . \
##   --resolution 1280x720 --quit-after 3000 \
##   --script res://tests/motion_p1_probe.gd

const ArenaScene = preload("res://scenes/main.tscn")


class Driver:
	extends Node

	const WARM := 60
	var arena: Node2D
	var out_dir := ""
	var wait := 0
	var initialized := false
	var busy := false
	var done := false
	var idx := 0
	var rows: Array = []
	var legacy_done := false


	func _scenes() -> Array:
		return [
			{"id": "stance", "phase": "discard", "phase_time": 0.30,
			 "winner": "", "rhythm_t": -1.0, "rhythm_winner": "",
			 "motion_id": "", "extra": ""},
			{"id": "reveal", "phase": "reveal", "phase_time": 0.75,
			 "winner": "", "rhythm_t": -1.0, "rhythm_winner": "",
			 "motion_id": "", "extra": ""},
			{"id": "player_win", "phase": "resolve", "phase_time": 0.80,
			 "winner": "player", "rhythm_t": 0.62,
			 "rhythm_winner": "player", "motion_id": "wave",
			 "extra": "super"},
			{"id": "enemy_win", "phase": "resolve", "phase_time": 0.80,
			 "winner": "enemy", "rhythm_t": 0.62,
			 "rhythm_winner": "enemy", "motion_id": "cross",
			 "extra": "launch"},
			{"id": "draw", "phase": "resolve", "phase_time": 0.12,
			 "winner": "draw", "rhythm_t": -1.0, "rhythm_winner": "",
			 "motion_id": "", "extra": ""},
			{"id": "legacy_player_win", "phase": "resolve",
			 "phase_time": 0.80, "winner": "player", "rhythm_t": 0.62,
			 "rhythm_winner": "player", "motion_id": "wave",
			 "extra": "super", "legacy_data": true},
		]


	func _inject(s: Dictionary) -> void:
		arena.tk_phase = String(s["phase"])
		arena.tk_phase_time = float(s["phase_time"])
		arena.tk_winner = String(s["winner"])
		arena.tk_rhythm_t = float(s["rhythm_t"])
		arena.tk_rhythm_winner = String(s["rhythm_winner"])
		arena.tk_motion_id = String(s["motion_id"])
		arena.tk_motion_extra = String(s["extra"])
		arena.tk_rhythm_hit = true
		if arena.layer_3d != null:
			arena.layer_3d.position = (arena.player.position
				+ arena.player.visual_shift)
		if arena.layer_3d_foe != null:
			arena.layer_3d_foe.position = (arena.enemy.position
				+ arena.enemy.visual_shift)


	func _drop_extra_tracks() -> void:
		# layer_3d.motion 与 arena.motion_3d 是同一个 Dictionary 引用
		# （_ready() 里直接 setup(motion_3d)），裁一份两层同时生效。
		for d in [arena.motion_3d, arena.motion_3d_foe]:
			var cards: Dictionary = d["cards"]
			for k in cards.keys():
				var nm := String(k)
				if nm != "jab" and nm != "cross" and nm != "wave":
					cards.erase(k)


	func _sv_png(label: String, layer, scene_id: String) -> String:
		var p := out_dir + "/mp1-" + scene_id + "-sv-" + label + ".png"
		if layer != null and layer.sv != null:
			var t = layer.sv.get_texture()
			if t != null:
				var im = t.get_image()
				if im != null:
					im.save_png(p)
		return p


	func _capture(s: Dictionary) -> Dictionary:
		var sid := String(s["id"])
		var lp = arena.layer_3d
		var lf = arena.layer_3d_foe
		var pc := ""
		var pf := -1
		var fc := ""
		var ff := -1
		if lp != null:
			pc = String(lp.last_card)
			pf = int(lp.last_frame)
		if lf != null:
			fc = String(lf.last_card)
			ff = int(lf.last_frame)
		var rec := {
			"id": sid, "phase": String(arena.tk_phase),
			"player_card": pc, "player_frame": pf,
			"foe_card": fc, "foe_frame": ff,
			"cards_at_scene": int(arena.motion_3d["cards"].size()),
			"player_sv": _sv_png("player", lp, sid),
			"foe_sv": _sv_png("foe", lf, sid),
			"live": out_dir + "/mp1-" + sid + "-live.png",
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
				"player_override": bool(arena.player.draw_3d_override),
				"enemy_override": bool(arena.enemy.draw_3d_override),
				"cards_player": int(arena.motion_3d["cards"].size()),
				"cards_foe": int(arena.motion_3d_foe["cards"].size()),
				"hp": [int(arena.player.hp), int(arena.enemy.hp)]}
			print("MOTION_P1_JSON " + JSON.stringify(payload))
			get_tree().quit(0)
			return
		var s: Dictionary = scenes[idx]
		var is_legacy: bool = bool(s.get("legacy_data", false))
		if is_legacy and not legacy_done:
			legacy_done = true
			_drop_extra_tracks()
		_inject(s)
		arena._sync_3d_layer()
		await RenderingServer.frame_post_draw
		var im := get_viewport().get_texture().get_image()
		var rec := _capture(s)
		rec["live_error"] = int(im.save_png(String(rec["live"])))
		rows.append(rec)
		idx += 1
		wait = WARM - 2
		busy = false


func _init() -> void:
	var out_dir := OS.get_environment("MOTION_P1_OUT")
	if out_dir == "":
		print("MOTION_P1_JSON " + JSON.stringify(
			{"error": "MOTION_P1_OUT missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var inst: Node2D = (ArenaScene as PackedScene).instantiate()
	root.add_child(inst)
	var d := Driver.new()
	d.arena = inst
	d.out_dir = out_dir
	root.add_child(d)
