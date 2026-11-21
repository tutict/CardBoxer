extends SceneTree
## P4 · 实机验收 · 真实自动对局逐帧采样探针。
##
## 与 P1/P2/P3/P4 的注入式探针不同：这里**不冻结 paused、不注入
## card/frame、不推进任何时钟、不覆盖任何 mapping 或动作表**，只开
## CARD_BOXER_TAIKOU_BOT=1（可选 CARD_BOXER_3D=1），让 arena.gd 自己
## 的 _tick_taikou() / _sync_3d_layer() 打完整局三回。
##
## 两种跑法共用本探针：
##   three_d      CARD_BOXER_3D=1：3D 层参与绘制，读回 13 骨 delta 与
##                两张 3D 运行时表的表标记（focus:8 的 f_knee）。
##   default_off  不设 3D：motion_3d 为空字典，2D 关节表才参与绘制；
##                读回 CardMotion._tracks 的 2D 表标记与整帧画面。
## P4 改的是 card_motion.json，只有 default_off 才能真正看到 2D 侧。
##
## 截图必须 await RenderingServer.frame_post_draw 后读纹理（B 路线实测
## 不等会拿到停滞帧缓冲）。跨 Godot 进程整局 RNG 会漂移，本探针不做
## 跨进程逐帧像素 A/B；A/B 走 Python 同源帧序列复算。
##
## 跑法：P4_LIVE_OUT=<abs> P4_LIVE_SEED=20261114 \
##   [CARD_BOXER_3D=1] CARD_BOXER_TAIKOU_BOT=1 \
##   godot --path . --resolution 1280x720 --quit-after 6000 \
##   --script res://tests/p4_live_probe.gd

const ArenaScene = preload("res://scenes/main.tscn")


class Driver:
	extends Node

	const SAMPLE_S := 0.12
	const MAX_T := 45.0
	const WARM := 30
	var arena: Node2D
	var out_dir := ""
	var seed_value := 20261114
	var t := 0.0
	var next_sample := 0.0
	var warm := 0
	var idx := 0
	var rows: Array = []
	var phase_changes: Array = []
	var last_phase := ""
	var last_round_phase := ""
	var was_fighting := false
	var done := false
	var busy := false
	var end_reason := ""
	var paused_violations := 0


	func _r3(x: float) -> float:
		return float(int(x * 1000.0)) / 1000.0


	## 3D 运行时表标记：取 focus:8 的 f_knee（P4 改动帧之一）。
	## 逐行按当前 (card, frame) 读回，证明引擎用的是落盘表而非旧表。
	func _marker_3d(m: Dictionary, card: String, frame: int) -> String:
		if m.is_empty() or not m.has("cards"):
			return "<off>"
		var kn: Array
		if card == "stance" or card == "":
			if not m.has("stance"):
				return "<no_stance>"
			kn = m["stance"]["f_knee"]
		else:
			var cards: Dictionary = m["cards"]
			if not cards.has(card):
				return "<no_card>"
			var tr: Array = cards[card]["track"]
			if frame < 0 or frame >= tr.size():
				return "<bad_frame>"
			kn = tr[frame]["f_knee"]
		return "%.6f|%.6f" % [float(kn[0]), float(kn[1])]


	func _marker_2d() -> String:
		CardMotion._ensure()
		var tr: Dictionary = CardMotion._tracks
		if not tr.has("focus"):
			return "<no_focus>"
		var a: Array = tr["focus"]
		if a.size() <= 8:
			return "<short_track>"
		var kn: Array = a[8]["f_knee"]
		return "%.6f|%.6f" % [float(kn[0]), float(kn[1])]


	func _sv_png(tag: String, layer, key: String) -> String:
		var p := out_dir + "/p4l-" + key + "-sv-" + tag + ".png"
		if layer != null and layer.sv != null:
			var tex = layer.sv.get_texture()
			if tex != null:
				var im = tex.get_image()
				if im != null:
					im.save_png(p)
		return p


	func _layer_state(layer) -> Dictionary:
		if layer == null:
			return {"card": "", "frame": -1,
					"frames_applied": 0, "delta": {}}
		var d := {}
		if layer.drv != null:
			d = layer.drv.last_delta_deg.duplicate()
		return {"card": String(layer.last_card),
				"frame": int(layer.last_frame),
				"frames_applied": int(layer.frames_applied),
				"delta": d}


	func _state() -> Dictionary:
		var use3 := bool(arena.use_3d)
		var cap := "<off>"
		var mode := "<off>"
		var mp := "<off>"
		var mf := "<off>"
		var pc := ""
		var pf := -1
		var fc := ""
		var ff := -1
		if arena.layer_3d != null:
			pc = String(arena.layer_3d.last_card)
			pf = int(arena.layer_3d.last_frame)
		if arena.layer_3d_foe != null:
			fc = String(arena.layer_3d_foe.last_card)
			ff = int(arena.layer_3d_foe.last_frame)
		if use3 and not arena.motion_3d.is_empty():
			var mg: Dictionary = arena.motion_3d["mapping"]
			cap = "%.4f" % float(mg["leg_cap_deg"])
			mode = String(mg.get("leg_mode", "<absent>"))
			mp = _marker_3d(arena.motion_3d, pc, pf)
			mf = _marker_3d(arena.motion_3d_foe, fc, ff)
		return {
			"t": _r3(t), "idx": idx,
			"round_phase": String(arena.round_phase),
			"tk_turn": int(arena.tk_turn),
			"tk_phase": String(arena.tk_phase),
			"tk_phase_time": _r3(float(arena.tk_phase_time)),
			"tk_rhythm_t": _r3(float(arena.tk_rhythm_t)),
			"tk_winner": String(arena.tk_winner),
			"tk_motion_id": String(arena.tk_motion_id),
			"tk_motion_extra": String(arena.tk_motion_extra),
			"hp": [int(arena.player.hp), int(arena.enemy.hp)],
			"round_wins": [int(arena.round_wins[0]),
				int(arena.round_wins[1])],
			"paused_live": bool(arena.paused),
			"use_3d": use3, "cap_live": cap, "mode_live": mode,
			"marker_player": mp, "marker_foe": mf,
			"player": _layer_state(arena.layer_3d),
			"foe": _layer_state(arena.layer_3d_foe),
		}


	func _finish() -> void:
		done = true
		CardMotion._ensure()
		var c2 := CardMotion._tracks.size()
		var f2 := 0
		for id: String in CardMotion._tracks:
			f2 += (CardMotion._tracks[id] as Array).size()
		var payload := {
			"rows": rows, "phase_changes": phase_changes,
			"seed": seed_value,
			"use_3d": bool(arena.use_3d),
			"tk_bot": bool(arena.tk_bot),
			"paused_violations": paused_violations,
			"env_3d": OS.get_environment("CARD_BOXER_3D"),
			"env_bot": OS.get_environment("CARD_BOXER_TAIKOU_BOT"),
			"cards_player": int(arena.motion_3d.get("cards", {}).size()),
			"cards_foe": int(arena.motion_3d_foe.get("cards", {}).size()),
			"cap_readback": float(arena.motion_3d.get(
				"mapping", {}).get("leg_cap_deg", -1.0)),
			"mode_readback": String(arena.motion_3d.get(
				"mapping", {}).get("leg_mode", "<absent>")),
			"marker_3d_player": _marker_3d(arena.motion_3d, "focus", 8),
			"marker_3d_foe": _marker_3d(arena.motion_3d_foe, "focus", 8),
			"marker_2d": _marker_2d(),
			"cards_2d": c2, "frames_2d": f2,
			"total_t": _r3(t), "end_reason": end_reason,
			"final_round_phase": String(arena.round_phase),
			"final_hp": [int(arena.player.hp), int(arena.enemy.hp)],
			"final_wins": [int(arena.round_wins[0]),
				int(arena.round_wins[1])],
			"sample_s": SAMPLE_S,
		}
		print("P4_LIVE_JSON " + JSON.stringify(payload))
		get_tree().quit(0)


	func _process(delta: float) -> void:
		if done or busy:
			return
		busy = true
		warm += 1
		if warm <= WARM:
			busy = false
			return
		t += delta
		if bool(arena.paused):
			paused_violations += 1
		var rp := String(arena.round_phase)
		var ph := "%d:%s" % [int(arena.tk_turn),
			String(arena.tk_phase)]
		var changed := (rp != last_round_phase) or (ph != last_phase)
		if changed:
			if rp != last_round_phase:
				phase_changes.append({"t": _r3(t),
					"kind": "round_phase", "value": rp})
			if ph != last_phase:
				phase_changes.append({"t": _r3(t),
					"kind": "tk_phase", "value": ph})
			last_round_phase = rp
			last_phase = ph
		if rp == "fight":
			was_fighting = true
			if t >= next_sample:
				next_sample = t + SAMPLE_S
				var key := "%04d" % idx
				var rec := _state()
				# 不等渲染帧完成会读到停滞帧缓冲，整帧图会假卡顿。
				await RenderingServer.frame_post_draw
				var action := (String(arena.tk_phase) == "reveal" \
						or String(arena.tk_phase) == "resolve")
				if action and rec["use_3d"]:
					rec["player_sv"] = _sv_png("player",
						arena.layer_3d, key)
					rec["foe_sv"] = _sv_png("foe",
						arena.layer_3d_foe, key)
				else:
					rec["player_sv"] = ""
					rec["foe_sv"] = ""
				if idx % 6 == 0 or changed:
					var live := out_dir + "/p4l-" + key + "-live.png"
					var im := get_viewport().get_texture().get_image()
					rec["live_error"] = int(im.save_png(live))
					rec["live"] = live
				else:
					rec["live"] = ""
				rows.append(rec)
				idx += 1
		if was_fighting and (rp == "over" or rp == "match_over"):
			end_reason = "round_over"
			_finish()
		elif t >= MAX_T:
			end_reason = "timeout"
			_finish()
		busy = false


func _init() -> void:
	var out_dir := OS.get_environment("P4_LIVE_OUT")
	if out_dir == "":
		print("P4_LIVE_JSON " + JSON.stringify(
			{"error": "P4_LIVE_OUT missing"}))
		quit(1)
		return
	var seed_s := OS.get_environment("P4_LIVE_SEED")
	var seed_v := 20261114
	if seed_s != "":
		seed_v = int(seed_s)
	# 在实例化 arena（会洗牌 / 发牌）之前固定全局 RNG
	seed(seed_v)
	DirAccess.make_dir_recursive_absolute(out_dir)
	var inst: Node2D = (ArenaScene as PackedScene).instantiate()
	root.add_child(inst)
	var d := Driver.new()
	d.arena = inst
	d.out_dir = out_dir
	d.seed_value = seed_v
	root.add_child(d)
