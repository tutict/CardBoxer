extends SceneTree
## H 路线：同一棵树、同一冻结状态的「双侧 3D」A/B 探针。
##
## 跨 Godot 进程逐像素对比不成立（全局 RNG 每次启动随机化，见
## tests/rng_probe.gd 与 engine-optimization/compare_regression.py 的订正）。
## 这里在同一个进程里：
##   ① 实例化 main.tscn 后立刻 paused，隐藏 HUD / fx，只留 World；
##   ② 抓 off 帧（两人都是既有 2D 自绘）；
##   ③ 原地挂两套 3D 表现层（玩家 / 对手各读自己的 motion），
##      两个 Fighter 都切 draw_3d_override；
##   ④ 逐阶段分别 apply 动作，各抓一帧。
## 于是 A/B 差异只可能来自两个 3D 层与骨架驱动。
##
## 跑法（必须带窗口）：
##   H_2SIDE_DIR=<abs> godot --path . --resolution 1280x720 \
##     --quit-after 900 --script res://tests/two_side_probe.gd

const ArenaScene = preload("res://scenes/main.tscn")
const LayerScript = preload("res://scripts/fighter_3d_layer.gd")
const MOTION_P := "res://data/motion_input.json"
const MOTION_F := "res://data/motion_input_foe.json"


class Driver:
	extends Node

	# 内部类有独立常量作用域，这里显式复制一份，不依赖作用域猜测。
	const LayerScript = preload("res://scripts/fighter_3d_layer.gd")
	const MOTION_P := "res://data/motion_input.json"
	const MOTION_F := "res://data/motion_input_foe.json"
	const WARM := 26
	const SHOTS := [
		{"name": "off", "p": "stance", "pf": 0, "f": "stance", "ff": 0},
		{"name": "both-stance", "p": "stance", "pf": 0, "f": "stance", "ff": 0},
		{"name": "player-jab6", "p": "jab", "pf": 6, "f": "stance", "ff": 0},
		{"name": "foe-cross11", "p": "stance", "pf": 0, "f": "cross", "ff": 11},
		{"name": "both-wave17", "p": "wave", "pf": 17, "f": "wave", "ff": 17},
	]

	var arena: Node2D
	var out_dir := ""
	var only := ""   # "" = 双侧；"player"/"foe" = 单侧隔离诊断
	var motion_p: Dictionary = {}
	var motion_f: Dictionary = {}
	var initialized := false
	var busy := false
	var stage := 0
	var wait := 0
	var player_ready := false
	var foe_ready := false
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
		var path := out_dir + "/h-" + name + ".png"
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

	## 诊断：层里第一个 MeshInstance3D 的节点名能区分两份 GLB
	## （player_HI_skinned vs foe_HI_skinned）。
	func _first_mesh_name(layer) -> String:
		if layer == null or layer.sv == null:
			return ""
		var stack: Array = []
		for c in layer.sv.get_children():
			stack.append(c)
		while not stack.is_empty():
			var n = stack.pop_back()
			if n is MeshInstance3D:
				return String(n.name)
			for c in n.get_children():
				stack.append(c)
		return ""

	## 返回 mesh 节点名 + 资源路径 + 顶点数，用来认出实际挂的是哪份 GLB。
	func _mesh_signature(layer) -> String:
		if layer == null or layer.sv == null:
			return ""
		var stack: Array = []
		for c in layer.sv.get_children():
			stack.append(c)
		while not stack.is_empty():
			var n = stack.pop_back()
			if n is MeshInstance3D:
				var m: Mesh = n.mesh
				var verts := 0
				if m is ArrayMesh:
					var arr: Array = (m as ArrayMesh).surface_get_arrays(0)
					if arr.size() > Mesh.ARRAY_VERTEX:
						verts = arr[Mesh.ARRAY_VERTEX].size()
				var sig := "%s|%s|%d" % [n.name, m.resource_path, verts]
				# 贴图资源路径：若两层指向同一张，就是材质缓存串味。
				var mat: Material = n.get_active_material(0)
				if mat is BaseMaterial3D:
					var t: Texture2D = (mat as BaseMaterial3D).albedo_texture
					if t != null:
						sig += "|albedo=" + String(t.resource_path)
				return sig
			for c in n.get_children():
				stack.append(c)
		return ""

	func _attach_layers() -> void:
		if only != "foe":
			_attach_player()
		if only != "player":
			_attach_foe()

	func _attach_player() -> void:
		var lp := LayerScript.new()
		arena.world.add_child(lp)
		player_ready = lp.setup(motion_p)
		if player_ready:
			arena.layer_3d = lp
			arena.motion_3d = motion_p
			# arena.paused 让 _sync_3d_layer() 不跑，位置必须由探针显式给，
			# 否则层留在 (0,0) 被画到画布外（G 路线首版踩过）。
			lp.position = arena.player.position + arena.player.visual_shift
			arena.player.draw_3d_override = true
			arena.player.queue_redraw()

	func _attach_foe() -> void:
		var lf := LayerScript.new()
		lf.configure("foe", LayerScript.FOE_GLB_PATH,
				LayerScript.DEFAULT_FOE_YAW, false)
		arena.world.add_child(lf)
		foe_ready = lf.setup(motion_f)
		if foe_ready:
			arena.layer_3d_foe = lf
			arena.motion_3d_foe = motion_f
			lf.position = arena.enemy.position + arena.enemy.visual_shift
			arena.enemy.draw_3d_override = true
			arena.enemy.queue_redraw()

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
			var pp: Variant = JSON.parse_string(
					FileAccess.get_file_as_string(MOTION_P))
			if pp is Dictionary:
				motion_p = pp
			var ff: Variant = JSON.parse_string(
					FileAccess.get_file_as_string(MOTION_F))
			if ff is Dictionary:
				motion_f = ff
		if wait >= WARM - 10:
			prims.append(Performance.get_monitor(
					Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME))
			calls.append(Performance.get_monitor(
					Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME))

		if stage == 0:
			wait += 1
			if wait >= WARM:
				await _snap("off")
				_attach_layers()
				stage = 1
				wait = 0
		elif stage < SHOTS.size():
			wait += 1
			var spec: Dictionary = SHOTS[stage]
			if arena.layer_3d != null:
				arena.layer_3d.apply(String(spec["p"]), int(spec["pf"]))
			if arena.layer_3d_foe != null:
				arena.layer_3d_foe.apply(String(spec["f"]), int(spec["ff"]))
			if wait >= WARM:
				await _snap(String(spec["name"]))
				stage += 1
				wait = 0
		else:
			var payload := {
				"shots": rows,
				"player_layer_ready": player_ready,
				"foe_layer_ready": foe_ready,
				"bones": int(arena.layer_3d.drv.bone_names.size())
						if arena.layer_3d != null else 0,
				"foe_bones": int(arena.layer_3d_foe.drv.bone_names.size())
						if arena.layer_3d_foe != null else 0,
				"player_frames_applied": int(arena.layer_3d.frames_applied)
						if arena.layer_3d != null else 0,
				"foe_frames_applied": int(arena.layer_3d_foe.frames_applied)
						if arena.layer_3d_foe != null else 0,
				"player_tex_drawn": bool(arena.layer_3d.tex_drawn)
						if arena.layer_3d != null else false,
				"foe_tex_drawn": bool(arena.layer_3d_foe.tex_drawn)
						if arena.layer_3d_foe != null else false,
				"player_yaw": float(arena.layer_3d.view_yaw_deg)
						if arena.layer_3d != null else 0.0,
				"foe_yaw": float(arena.layer_3d_foe.view_yaw_deg)
						if arena.layer_3d_foe != null else 0.0,
				"foe_role": String(arena.layer_3d_foe.role_id)
						if arena.layer_3d_foe != null else "",
				"player_override": bool(arena.player.draw_3d_override),
				"enemy_override": bool(arena.enemy.draw_3d_override),
				"player_glb_path": String(arena.layer_3d.glb_path)
						if arena.layer_3d != null else "",
				"foe_glb_path": String(arena.layer_3d_foe.glb_path)
						if arena.layer_3d_foe != null else "",
				"player_mesh_name": _first_mesh_name(arena.layer_3d),
				"foe_mesh_name": _first_mesh_name(arena.layer_3d_foe),
				"player_mesh_sig": _mesh_signature(arena.layer_3d),
				"foe_mesh_sig": _mesh_signature(arena.layer_3d_foe),
				"sv_same": (arena.layer_3d != null
						and arena.layer_3d_foe != null
						and arena.layer_3d.sv == arena.layer_3d_foe.sv),
				"tex_same": (arena.layer_3d != null
						and arena.layer_3d_foe != null
						and arena.layer_3d.sv.get_texture()
						== arena.layer_3d_foe.sv.get_texture()),
				"use_3d_env": OS.get_environment("CARD_BOXER_3D"),
				"only": only,
			}
			var f := FileAccess.open(out_dir + "/ab_result.json",
					FileAccess.WRITE)
			if f != null:
				f.store_string(JSON.stringify(payload, "\t"))
				f.close()
			print("H2SIDE_JSON " + JSON.stringify(payload))
			get_tree().quit(0)
			return
		busy = false


func _init() -> void:
	var out_dir := OS.get_environment("H_2SIDE_DIR")
	if out_dir == "":
		print("H2SIDE_JSON " + JSON.stringify({"error": "H_2SIDE_DIR missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var inst: Node2D = (ArenaScene as PackedScene).instantiate()
	root.add_child(inst)
	var d := Driver.new()
	d.arena = inst
	d.out_dir = out_dir
	d.only = OS.get_environment("H_2SIDE_ONLY")
	root.add_child(d)
	print("H2SIDE_START out=%s" % out_dir)
