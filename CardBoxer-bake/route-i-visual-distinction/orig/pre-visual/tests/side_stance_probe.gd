extends SceneTree
## G 路线「侧面战斗」站架偏置探针：固定 +55° 侧视，扫 4 档骨骼偏置。
##
## 目的：正视 A-pose 平举双臂在侧面视角下完全不像格斗。这里在表现层
## 给 13 骨 pose 叠加一个静态旋转偏置，把双臂收成护脸站架、前后脚分开。
## rig_driver.gd / motion_input.json / 73 帧表一个字不改；默认偏置为空。
##
## 跑法（必须带窗口）：
##   G_STANCE_DIR=<abs> godot --path . --resolution 1280x720 \
##     --quit-after 1200 --script res://tests/side_stance_probe.gd

const ArenaScene = preload("res://scenes/main.tscn")
const LayerScript = preload("res://scripts/fighter_3d_layer.gd")
const MOTION_PATH := "res://data/motion_input.json"
const WARM := 8
const FIXED_YAW := 55.0
# 站架候选由 G_STANCE_CASES(JSON) 注入，探针脚本本身不用为换候选而改。
# 单位 = 度，绕 Z，与 rig_driver 的 delta 同符号口径。


class Driver:
	extends Node

	const WARM := 8
	const MOTION_PATH := "res://data/motion_input.json"
	const FIXED_YAW := 55.0

	var arena: Node2D
	var out_dir := ""
	var motion: Dictionary = {}
	var cases: Array = []
	var initialized := false
	var busy := false
	var stage := 0
	var wait := 0
	var layer_ready := false
	var rows: Array = []

	func _snap(name: String) -> void:
		await RenderingServer.frame_post_draw
		var img := get_viewport().get_texture().get_image()
		var path := out_dir + "/stance-" + name + ".png"
		var err := img.save_png(path)
		rows.append({"name": name, "path": path,
				"w": img.get_width(), "h": img.get_height(),
				"save_error": int(err)})

	func _process(_d: float) -> void:
		if busy:
			return
		busy = true
		if not initialized:
			initialized = true
			arena.paused = true
			for c in arena.get_children():
				if c.name != "World":
					c.visible = false
			var parsed: Variant = JSON.parse_string(
					FileAccess.get_file_as_string(MOTION_PATH))
			if parsed is Dictionary:
				motion = parsed
			var l := LayerScript.new()
			arena.world.add_child(l)
			layer_ready = l.setup(motion)
			if layer_ready:
				arena.layer_3d = l
				arena.motion_3d = motion
				l.position = arena.player.position + arena.player.visual_shift
				l.set_view(FIXED_YAW, false)
				arena.player.draw_3d_override = true
				arena.player.queue_redraw()
			stage = 0
			wait = 0
		if wait < WARM:
			wait += 1
			busy = false
			return
		if layer_ready and stage < cases.size():
			var v: Dictionary = cases[stage]
			arena.layer_3d.set_stance_bias(v["bias"])
			arena.layer_3d.apply("stance", 0)
			await _snap(String(v["name"]))
			stage += 1
			wait = 0
		else:
			var payload := {
				"shots": rows, "layer_ready": layer_ready,
				"cases_count": cases.size(), "fixed_yaw": FIXED_YAW,
				"bones": int(arena.layer_3d.drv.bone_names.size())
						if arena.layer_3d != null else 0,
				"final_bias_keys": arena.layer_3d.stance_bias_deg.keys()
						if arena.layer_3d != null else [],
			}
			var f := FileAccess.open(out_dir + "/stance_result.json",
					FileAccess.WRITE)
			if f != null:
				f.store_string(JSON.stringify(payload, "\t"))
				f.close()
			print("G_STANCE_JSON " + JSON.stringify(payload))
			get_tree().quit(0)
			return
		busy = false


func _init() -> void:
	var out_dir := OS.get_environment("G_STANCE_DIR")
	if out_dir == "":
		print("G_STANCE_JSON " + JSON.stringify({"error": "G_STANCE_DIR missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var inst: Node2D = (ArenaScene as PackedScene).instantiate()
	root.add_child(inst)
	var d := Driver.new()
	d.arena = inst
	d.out_dir = out_dir
	var raw := OS.get_environment("G_STANCE_CASES")
	var parsed: Variant = JSON.parse_string(raw)
	if parsed is Array:
		d.cases = parsed
	root.add_child(d)
	print("G_STANCE_START out=%s cases=%d" % [out_dir, d.cases.size()])
