extends SceneTree
## G 路线「侧面战斗」角度探针：同一棵树、同一冻结状态扫相机 yaw 与贴图镜像。
##
## 跨 Godot 进程逐像素对比不成立（全局 RNG 每次启动随机化），所以这里
## 在一个进程里挂一次 3D 层，逐组只改相机 + 镜像，固定同一动作帧截一张。
## 骨架 driver 完全不动：证明「侧面战斗」是纯观察层改动。
##
## 跑法（必须带窗口）：
##   G_SIDE_DIR=<abs> godot --path . --resolution 1280x720 \
##     --quit-after 1200 --script res://tests/side_view_probe.gd

const ArenaScene = preload("res://scenes/main.tscn")
const LayerScript = preload("res://scripts/fighter_3d_layer.gd")
const MOTION_PATH := "res://data/motion_input.json"
const WARM := 8

# yaw 为相机绕 +Y 的角度；负 yaw = 相机移到角色左前方 = 看到脸朝画面右。
# flip 是 ViewportTexture 的水平镜像，用来在不转相机时换朝向。
const VIEWS := [
	{"name": "y000-f0", "yaw": 0.0, "flip": false},
	{"name": "y000-f1", "yaw": 0.0, "flip": true},
	{"name": "ym35-f0", "yaw": -35.0, "flip": false},
	{"name": "ym35-f1", "yaw": -35.0, "flip": true},
	{"name": "ym55-f0", "yaw": -55.0, "flip": false},
	{"name": "ym55-f1", "yaw": -55.0, "flip": true},
	{"name": "yp35-f0", "yaw": 35.0, "flip": false},
	{"name": "yp55-f0", "yaw": 55.0, "flip": false},
]


class Driver:
	extends Node

	# 内部类独立常量作用域，显式复制，别依赖 GDScript 的作用域猜测。
	const WARM := 8
	const MOTION_PATH := "res://data/motion_input.json"
	const VIEWS := [
		{"name": "y000-f0", "yaw": 0.0, "flip": false},
		{"name": "y000-f1", "yaw": 0.0, "flip": true},
		{"name": "ym35-f0", "yaw": -35.0, "flip": false},
		{"name": "ym35-f1", "yaw": -35.0, "flip": true},
		{"name": "ym55-f0", "yaw": -55.0, "flip": false},
		{"name": "ym55-f1", "yaw": -55.0, "flip": true},
		{"name": "yp35-f0", "yaw": 35.0, "flip": false},
		{"name": "yp55-f0", "yaw": 55.0, "flip": false},
	]

	var arena: Node2D
	var out_dir := ""
	var motion: Dictionary = {}
	var initialized := false
	var busy := false
	var stage := 0
	var wait := 0
	var layer_ready := false
	var rows: Array = []

	func _snap(name: String) -> void:
		await RenderingServer.frame_post_draw
		var img := get_viewport().get_texture().get_image()
		var path := out_dir + "/side-" + name + ".png"
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
				# arena.paused 让 _sync_3d_layer() 不跑，位置必须显式给。
				l.position = arena.player.position + arena.player.visual_shift
				arena.player.draw_3d_override = true
				arena.player.queue_redraw()
			stage = 0
			wait = 0
		if wait < WARM:
			wait += 1
			busy = false
			return
		if layer_ready and stage < VIEWS.size():
			var v: Dictionary = VIEWS[stage]
			arena.layer_3d.set_view(float(v["yaw"]), bool(v["flip"]))
			# 固定同一动作帧：jab f6 是已验的出手帧，能看出侧向压缩。
			arena.layer_3d.apply("jab", 6)
			await _snap(String(v["name"]))
			stage += 1
			wait = 0
		else:
			var payload := {
				"shots": rows, "layer_ready": layer_ready,
				"views_count": VIEWS.size(),
				"view_changes": int(arena.layer_3d.view_changes)
						if arena.layer_3d != null else 0,
				"final_yaw": float(arena.layer_3d.view_yaw_deg)
						if arena.layer_3d != null else 0.0,
				"final_flip": bool(arena.layer_3d.view_flip)
						if arena.layer_3d != null else false,
				"bones": int(arena.layer_3d.drv.bone_names.size())
						if arena.layer_3d != null else 0,
			}
			var f := FileAccess.open(out_dir + "/side_result.json",
					FileAccess.WRITE)
			if f != null:
				f.store_string(JSON.stringify(payload, "\t"))
				f.close()
			print("G_SIDE_JSON " + JSON.stringify(payload))
			get_tree().quit(0)
			return
		busy = false


func _init() -> void:
	var out_dir := OS.get_environment("G_SIDE_DIR")
	if out_dir == "":
		print("G_SIDE_JSON " + JSON.stringify({"error": "G_SIDE_DIR missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var inst: Node2D = (ArenaScene as PackedScene).instantiate()
	root.add_child(inst)
	var d := Driver.new()
	d.arena = inst
	d.out_dir = out_dir
	root.add_child(d)
	print("G_SIDE_START out=%s" % out_dir)
