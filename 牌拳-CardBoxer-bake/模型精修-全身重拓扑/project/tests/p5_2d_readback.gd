extends SceneTree
## P5 · 2D 侧引擎读回：CardMotion._tracks（运行时真正拿到的那份）
## vs orig/pre-p5 的 P4 上线态原表。
##
## 3D 开态下 fighter.gd::_draw() 只画影子就 early return，2D 关节表不参与
## 绘制，所以做不了「3D 开态的 2D 像素 A/B」。这里让引擎自己读回运行时表，
## 量化改动范围，并用引擎读回的关节轨独立算 mf 峰值（不靠 Python 报告）。
##
## 期望 mf 由 P5_EXPECT_MF 传入，来源是 p5_readback.py 的独立读回结果。
##
## 跑法：P5_ORIG=<abs> P5_EXPECT_MF='{"wave":60.823,...}' \
##   godot --headless --path . --script res://tests/p5_2d_readback.gd


func _read_json(path: String) -> Dictionary:
	var txt := FileAccess.get_file_as_string(path)
	var parsed: Variant = JSON.parse_string(txt)
	if typeof(parsed) != TYPE_DICTIONARY:
		return {}
	return parsed as Dictionary


func _peak_mf(track: Array, st: Vector2) -> Dictionary:
	var best := -1.0
	var best_i := -1
	for i in range(track.size()):
		var fh: Array = (track[i] as Dictionary).get("f_hand", [])
		if fh.size() != 2:
			continue
		var d := Vector2(float(fh[0]), float(fh[1])).distance_to(st)
		if d > best:
			best = d
			best_i = i
	return {"peak": best, "frame": best_i}


func _init() -> void:
	var orig := OS.get_environment("P5_ORIG")
	var expect_txt := OS.get_environment("P5_EXPECT_MF")
	if orig == "" or expect_txt == "":
		print("P5_2D_JSON " + JSON.stringify(
			{"error": "P5_ORIG/P5_EXPECT_MF missing"}))
		quit(1)
		return
	var expect: Variant = JSON.parse_string(expect_txt)
	if typeof(expect) != TYPE_DICTIONARY:
		print("P5_2D_JSON " + JSON.stringify(
			{"error": "expect mf parse"}))
		quit(1)
		return
	CardMotion._ensure()
	var shipped: Dictionary = CardMotion._tracks
	var legacy_file := _read_json(orig + "/card_motion.json")
	var cur_file := _read_json("res://data/card_motion.json")
	var legacy: Dictionary = legacy_file.get("cards", {})
	var st_raw: Array = (cur_file.get("stance", {}) as Dictionary).get(
		"f_hand", [])
	if st_raw.size() != 2:
		print("P5_2D_JSON " + JSON.stringify(
			{"error": "stance f_hand missing"}))
		quit(1)
		return
	var st := Vector2(float(st_raw[0]), float(st_raw[1]))

	var arm_joints := ["f_elbow", "f_hand", "b_elbow", "b_hand"]
	var editable := ["wave", "cross"]
	var max_d := 0.0
	var changed := {}
	var scope_bad: Array = []
	var jab_changes := 0
	var missing: Array = []
	var card_n := 0
	var frame_n := 0
	for id: String in shipped:
		if not legacy.has(id):
			missing.append(id)
			continue
		card_n += 1
		var a: Array = shipped[id]
		var b: Array = legacy[id]["track"]
		if a.size() != b.size():
			missing.append(id + ":len")
			continue
		frame_n += a.size()
		for i in range(a.size()):
			var fa: Dictionary = a[i]
			var fb: Dictionary = b[i]
			for k: String in CardMotion.JOINTS:
				var va: Array = fa[k]
				var vb: Array = fb[k]
				var dx: float = float(va[0]) - float(vb[0])
				var dy: float = float(va[1]) - float(vb[1])
				var dist := sqrt(dx * dx + dy * dy)
				max_d = maxf(max_d, dist)
				if dist > 1e-6:
					if not changed.has(id):
						changed[id] = {}
					(changed[id] as Dictionary)[i] = true
					if not (editable.has(id) and arm_joints.has(k)):
						scope_bad.append("%s/%d/%s" % [id, i, k])
					if id == "jab":
						jab_changes += 1
		# 端点保护：首帧/末帧 11 关节逐点必须与基线相同
		for idx in [0, a.size() - 1]:
			var fa: Dictionary = a[idx]
			var fb: Dictionary = b[idx]
			for k: String in CardMotion.JOINTS:
				var va: Array = fa[k]
				var vb: Array = fb[k]
				if absf(float(va[0]) - float(vb[0])) > 1e-6 \
						or absf(float(va[1]) - float(vb[1])) > 1e-6:
					scope_bad.append("%s/endpoint%d/%s" % [id, idx, k])

	var changed_frames := 0
	for id: Variant in changed:
		changed_frames += (changed[id] as Dictionary).size()

	var peaks := {}
	var mf_bad: Array = []
	for id: Variant in (expect as Dictionary):
		if not shipped.has(String(id)):
			mf_bad.append(String(id) + ":missing")
			continue
		var got := _peak_mf(shipped[String(id)], st)
		peaks[String(id)] = {
			"peak": round(got["peak"] * 10000.0) / 10000.0,
			"frame": got["frame"]}
		var want: float = float((expect as Dictionary)[id])
		if absf(float(got["peak"]) - want) > 1e-3:
			mf_bad.append("%s:got=%.4f want=%.4f" % [
				String(id), float(got["peak"]), want])

	var checks := {
		"cardmotion_loaded": not shipped.is_empty(),
		"all_legacy_cards_present": missing.is_empty(),
		"only_wave_cross_four_arm_joints_changed": scope_bad.is_empty(),
		"jab_track_unchanged_in_engine": jab_changes == 0,
		"changed_frame_count_is_42": changed_frames == 42,
		"max_joint_delta_is_40px": absf(max_d - 40.0) < 1e-3,
		"mf_peaks_match_independent_readback": mf_bad.is_empty(),
		"cards_and_frames_positive": card_n > 0 and frame_n > 0,
	}
	var ok := true
	for k: Variant in checks:
		if not checks[k]:
			ok = false
	var payload := {
		"cards": card_n, "frames": frame_n,
		"changed_frames": changed_frames,
		"max_joint_delta_px": round(max_d * 10000.0) / 10000.0,
		"scope_violations": scope_bad.slice(0, 20),
		"jab_changes": jab_changes, "missing": missing,
		"mf_peaks_engine": peaks, "mf_mismatches": mf_bad,
		"checks": checks, "ok": ok,
	}
	print("P5_2D_JSON " + JSON.stringify(payload))
	quit(0 if ok else 1)
