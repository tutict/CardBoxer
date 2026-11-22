extends SceneTree
## G 路线：同一棵树、同一冻结状态的 3D 双轨 A/B 探针。
##
## 跨 Godot 进程的逐像素对比不成立（全局 RNG 每次启动随机化，见
## tests/rng_probe.gd 与 engine-optimization/compare_regression.py 的订正）。
## 这里在**同一个进程**里：
##   ① 实例化 main.tscn 后立刻 paused，隐藏 HUD / fx，只留 World；
##   ② 抓 off 帧（无 3D 层）；
##   ③ 原地挂上 3D 表现层、把玩家切到 draw_3d_override；
##   ④ 逐帧 apply stance / jab6 / wave17 并各抓一帧。
## 于是 A/B 差异只可能来自 3D 层与骨架驱动，手牌、抖动、相位全部共用。
##
## 跑法（必须带窗口）：
##   G_3D_AB_DIR=<abs> godot --path . --resolution 1280x720 \
##     --quit-after 900 --script res://tests/three_d_probe.gd

const ArenaScene = preload("res://scenes/main.tscn")
const LayerScript = preload("res://scripts/fighter_3d_layer.gd")
const MOTION_PATH := "res://data/motion_input.json"

const WARM := 26
const SHOTS := [
	{"name": "off", "card": "", "frame": 0},
	{"name": "on-stance", "card": "stance", "frame": 0},
	{"name": "on-jab6", "card": "jab", "frame": 6},
	{"name": "on-wave17", "card": "wave", "frame": 17},
]


class Driver:
	extends Node

	# 内部类有独立常量作用域，外部脚本常量不能按名字直接访问；
	# 这里显式复制一份，避免依赖 GDScript 的作用域猜测。
	const WARM := 26
	const MOTION_PATH := "res://data/motion_input.json"
	const SHOTS := [
		{"name": "off", "card": "", "frame": 0},
		{"name": "on-stance", "card": "stance", "frame": 0},
		{"name": "on-jab6", "card": "jab", "frame": 6},
		{"name": "on-wave17", "card": "wave", "frame": 17},
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
	var prims: Array = []
	var calls: Array = []

	func _avg(a: Array) -> float:
		if a.is_empty():
			return 0.0
		var s := 0.0
		for x in a:
			s += float(x)
		return s / float(a.size())

	func _snap(name: String) -> void:
		await RenderingServer.frame_post_draw
		var img := get_viewport().get_texture().get_image()
		var path := out_dir + "/ab-" + name + ".png"
		var err := img.save_png(path)
		rows.append({
			"name": name, "path": path,
			"w": img.get_width(), "h": img.get_height(),
			"save_error": int(err),
			"prims_mean": _avg(prims),
			"draw_calls_mean": _avg(calls),
		})
		prims.clear()
		calls.clear()

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
		# 只取每阶段末尾 10 帧的稳态：挂 3D 层那一帧要同步载入
		# 38 MB GLB + 3 张 4096² 贴图，会污染帧时间。
		# 不用 TIME_PROCESS：本探针的 await frame_post_draw 会让下一帧
		# monitor 出现数百毫秒级的假值；只用两个可复核的渲染计数。
		if wait >= WARM - 10:
			prims.append(Performance.get_monitor(
					Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME))
			calls.append(Performance.get_monitor(
					Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME))

		if stage == 0:
			wait += 1
			if wait >= WARM:
				await _snap("off")
				var l := LayerScript.new()
				arena.world.add_child(l)
				layer_ready = l.setup(motion)
				if layer_ready:
					arena.layer_3d = l
					arena.motion_3d = motion
					# arena.paused 让 _sync_3d_layer() 不跑，位置必须由探针
					# 显式给，否则层留在 (0,0) 被画到画布外（首版踩过）。
					l.position = arena.player.position + arena.player.visual_shift
					arena.player.draw_3d_override = true
					arena.player.queue_redraw()
				stage = 1
				wait = 0
		elif stage < SHOTS.size():
			wait += 1
			var spec: Dictionary = SHOTS[stage]
			if arena.layer_3d != null:
				arena.layer_3d.apply(String(spec["card"]), int(spec["frame"]))
			if wait >= WARM:
				await _snap(String(spec["name"]))
				stage += 1
				wait = 0
		else:
			var payload := {
				"shots": rows,
				"layer_ready": layer_ready,
				"motion_cards": motion.get("cards", {}).keys(),
				"bones": int(arena.layer_3d.drv.bone_names.size())
						if arena.layer_3d != null else 0,
				"frames_applied": int(arena.layer_3d.frames_applied)
						if arena.layer_3d != null else 0,
				"tex_drawn": bool(arena.layer_3d.tex_drawn)
						if arena.layer_3d != null else false,
				"last_card": String(arena.layer_3d.last_card)
						if arena.layer_3d != null else "",
				"last_frame": int(arena.layer_3d.last_frame)
						if arena.layer_3d != null else -1,
				"draw_3d_override": bool(arena.player.draw_3d_override),
				"use_3d_env": OS.get_environment("CARD_BOXER_3D"),
			}
			var f := FileAccess.open(out_dir + "/ab_result.json",
					FileAccess.WRITE)
			if f != null:
				f.store_string(JSON.stringify(payload, "\t"))
				f.close()
			print("G3D_AB_JSON " + JSON.stringify(payload))
			get_tree().quit(0)
			return
		busy = false


func _init() -> void:
	var out_dir := OS.get_environment("G_3D_AB_DIR")
	if out_dir == "":
		print("G3D_AB_JSON " + JSON.stringify({"error": "G_3D_AB_DIR missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var inst: Node2D = (ArenaScene as PackedScene).instantiate()
	root.add_child(inst)
	var d := Driver.new()
	d.arena = inst
	d.out_dir = out_dir
	root.add_child(d)
	print("G3D_AB_START out=%s" % out_dir)
