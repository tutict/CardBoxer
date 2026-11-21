extends SceneTree
## P4 · 2D 侧引擎读回：CardMotion 实际加载的招式表 vs P3 上线态原表。
##
## 3D 开态下 fighter.gd::_draw() 只画影子就 early return，2D 关节表不参与
## 绘制，所以做不了「3D 开态的 2D 像素 A/B」。这里退一步，让引擎自己读回
## CardMotion._tracks（运行时真正拿到的那份），逐帧量化 11 关节位移，
## 并断言只有四个腿关节变化、位移不足 2px。
##
## 跑法：P4_ORIG=<abs> godot --headless --path . \
##   --script res://tests/p4_2d_readback.gd


func _init() -> void:
	var orig := OS.get_environment("P4_ORIG")
	var leg_joints := ["f_knee", "f_foot", "b_knee", "b_foot"]
	if orig == "":
		print("P4_2D_JSON " + JSON.stringify({"error": "P4_ORIG missing"}))
		quit(1)
		return
	CardMotion._ensure()
	var shipped: Dictionary = CardMotion._tracks
	var txt := FileAccess.get_file_as_string(orig + "/card_motion.json")
	var parsed: Variant = JSON.parse_string(txt)
	if typeof(parsed) != TYPE_DICTIONARY:
		print("P4_2D_JSON " + JSON.stringify({"error": "legacy parse"}))
		quit(1)
		return
	var legacy: Dictionary = (parsed as Dictionary).get("cards", {})
	var max_d := 0.0
	var changed_frames := 0
	var non_leg_changes := 0
	var cards := 0
	var frames := 0
	var missing := []
	for id: String in shipped:
		if not legacy.has(id):
			missing.append(id)
			continue
		cards += 1
		var a: Array = shipped[id]
		var b: Array = legacy[id]["track"]
		frames += a.size()
		if a.size() != b.size():
			missing.append(id + ":len")
			continue
		for i in range(a.size()):
			var fa: Dictionary = a[i]
			var fb: Dictionary = b[i]
			var worst := 0.0
			for k: String in CardMotion.JOINTS:
				var va: Array = fa[k]
				var vb: Array = fb[k]
				var dx: float = float(va[0]) - float(vb[0])
				var dy: float = float(va[1]) - float(vb[1])
				var dist := sqrt(dx * dx + dy * dy)
				worst = maxf(worst, dist)
				if dist > 1e-6 and not leg_joints.has(k):
					non_leg_changes += 1
			if worst > 1e-6:
				changed_frames += 1
			max_d = maxf(max_d, worst)
	var checks := {
		"cardmotion_loaded": not shipped.is_empty(),
		"all_legacy_cards_present": missing.is_empty(),
		"only_four_leg_joints_changed": non_leg_changes == 0,
		"max_displacement_under_2px": max_d < 2.0,
		"some_frames_changed": changed_frames > 0,
		"cards_and_frames_positive": cards > 0 and frames > 0,
	}
	var ok := true
	for k in checks:
		if not checks[k]:
			ok = false
	var payload := {
		"cards": cards, "frames": frames,
		"changed_frames": changed_frames,
		"max_joint_delta_px": round(max_d * 10000.0) / 10000.0,
		"non_leg_changes": non_leg_changes,
		"missing": missing, "checks": checks, "ok": ok,
	}
	print("P4_2D_JSON " + JSON.stringify(payload))
	quit(0 if ok else 1)
