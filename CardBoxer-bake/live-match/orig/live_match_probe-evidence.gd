extends SceneTree
## B 路线 · 真实自动对局逐帧采样探针。
##
## 与 P1/P2 的注入式探针不同：这里**不冻结 paused、不注入 card/frame、
## 不推进任何时钟**，只开 CARD_BOXER_3D=1 + CARD_BOXER_TAIKOU_BOT=1，
## 让 arena.gd 自己的 _tick_taikou() / _sync_3d_layer() 打完整局三回。
## 探针只做两件事：每 0.12 s 读回运行时状态，并保存 SubViewport / 整帧
## 原图。游戏源码、动作表、判定、阶段时长一律不动。
##
## LIVE_MATCH_CAP 非空时，运行时把两份 mapping 的 leg_cap_deg 设为该值
## （同种子 cap3 / cap9 A/B）；为空则完全使用落盘值，不覆盖。
## LIVE_MATCH_SEED 固定全局 RNG 种子，让两局牌型可复现。
## 注：截图不 await frame_post_draw，SubViewport 渲染结果最多滞后状态
## 1 帧；连贯性结论以数值 delta 序列为准，图片只作视觉佐证。
##
## 跑法：LIVE_MATCH_OUT=<abs> CARD_BOXER_3D=1 CARD_BOXER_TAIKOU_BOT=1 \
##   godot --path . --resolution 1280x720 --quit-after 6000 \
##   --script res://tests/live_match_probe.gd

const ArenaScene = preload("res://scenes/main.tscn")


class Driver:
	extends Node

	const SAMPLE_S := 0.12
	const MAX_T := 45.0
	const WARM := 30
	var arena: Node2D
	var out_dir := ""
	var cap_override := -1.0
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


	func _r3(x: float) -> float:
		return float(int(x * 1000.0)) / 1000.0


	func _set_cap(cap: float) -> void:
		if arena.motion_3d == null or arena.motion_3d_foe == null:
			return
		if arena.motion_3d.is_empty() or arena.motion_3d_foe.is_empty():
			return
		arena.motion_3d["mapping"]["leg_cap_deg"] = cap
		arena.motion_3d_foe["mapping"]["leg_cap_deg"] = cap


	func _sv_png(tag: String, layer, key: String) -> String:
		var p := out_dir + "/lm-" + key + "-sv-" + tag + ".png"
		if layer != null and layer.sv != null:
			var tex = layer.sv.get_texture()
			if tex != null:
				var im = tex.get_image()
				if im != null:
					im.save_png(p)
		return p


	func _layer_state(layer) -> Dictionary:
		if layer == null:
			return {}
		var d := {}
		if layer.drv != null:
			d = layer.drv.last_delta_deg.duplicate()
		return {"card": String(layer.last_card),
				"frame": int(layer.last_frame),
				"frames_applied": int(layer.frames_applied),
				"delta": d}


	func _state() -> Dictionary:
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
			"tk_rhythm_winner": String(arena.tk_rhythm_winner),
			"hp": [int(arena.player.hp), int(arena.enemy.hp)],
			"round_wins": [int(arena.round_wins[0]),
				int(arena.round_wins[1])],
			"player": _layer_state(arena.layer_3d),
			"foe": _layer_state(arena.layer_3d_foe),
			"cap_live": float(arena.motion_3d["mapping"]["leg_cap_deg"]),
		}


	func _finish() -> void:
		done = true
		var payload := {
			"rows": rows, "phase_changes": phase_changes,
			"seed": seed_value, "cap_override": cap_override,
			"cap_readback": float(
				arena.motion_3d["mapping"]["leg_cap_deg"]),
			"use_3d": bool(arena.use_3d),
			"tk_bot": bool(arena.tk_bot),
			"cards_player": int(arena.motion_3d["cards"].size()),
			"cards_foe": int(arena.motion_3d_foe["cards"].size()),
			"env_3d": OS.get_environment("CARD_BOXER_3D"),
			"env_bot": OS.get_environment("CARD_BOXER_TAIKOU_BOT"),
			"total_t": _r3(t), "end_reason": end_reason,
			"final_round_phase": String(arena.round_phase),
			"final_hp": [int(arena.player.hp), int(arena.enemy.hp)],
			"final_wins": [int(arena.round_wins[0]),
				int(arena.round_wins[1])],
			"sample_s": SAMPLE_S,
		}
		print("LIVE_MATCH_JSON " + JSON.stringify(payload))
		get_tree().quit(0)


	func _process(delta: float) -> void:
		if done or busy:
			return
		busy = true
		warm += 1
		if warm <= WARM:
			busy = false
			return
		if cap_override > 0.0:
			_set_cap(cap_override)
		t += delta
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
				# 必须等渲染帧完成再读纹理：不等时 get_image() 会拿到
				# 停滞的帧缓冲，实测连续多个采样点 PNG 逐字节相同
				# （0017..0020 全同、后段整帧 6 张全同），GIF 会假卡顿。
				# 与 P1/P2 注入式探针同一口径。
				await RenderingServer.frame_post_draw
				var action := (String(arena.tk_phase) == "reveal" \
						or String(arena.tk_phase) == "resolve")
				if action:
					rec["player_sv"] = _sv_png("player",
						arena.layer_3d, key)
					rec["foe_sv"] = _sv_png("foe",
						arena.layer_3d_foe, key)
				else:
					rec["player_sv"] = ""
					rec["foe_sv"] = ""
				if idx % 6 == 0 or changed:
					var live := out_dir + "/lm-" + key + "-live.png"
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
	var out_dir := OS.get_environment("LIVE_MATCH_OUT")
	if out_dir == "":
		print("LIVE_MATCH_JSON " + JSON.stringify(
			{"error": "LIVE_MATCH_OUT missing"}))
		quit(1)
		return
	var cap_s := OS.get_environment("LIVE_MATCH_CAP")
	var seed_s := OS.get_environment("LIVE_MATCH_SEED")
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
	if cap_s != "":
		d.cap_override = float(cap_s)
	root.add_child(d)
