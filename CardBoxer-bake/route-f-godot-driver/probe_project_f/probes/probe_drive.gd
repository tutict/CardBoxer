extends SceneTree
## 阶段 4b：带窗口数值探针 —— 验证运行时驱动层的数学口径。
##
## 为什么必须带窗口：headless 的 dummy driver 不发 frame_post_draw，
## Skeleton3D 的 global pose 脏标记不刷新，get_bone_global_pose 会一直
## 返回 rest（C 路线 pose_probe.gd 已实测）。这里每帧驱动后等一帧真实
## 渲染，再读 engine global pose，才是真的「引擎算出来的骨架」。
##
## 三重对账（crosscheck_godot_pose.py 独立复算）：
##   ① GDScript 现算 delta_deg      vs rig_frames.json Blender 基准
##   ② GDScript 算 calc_global_origin vs 引擎 get_bone_global_pose
##   ③ 引擎 global_pose             vs Blender global_pos（映射 x,z,-y）
## 另外逐帧记录 pose 的「写入即读回」，证明驱动层真的写进了 Skeleton3D。
##
## 用法：F_SHOT_DIR=<abs> godot --path <proj> --script res://probes/probe_drive.gd
##       本探针不存图，只输出 DRIVE_JSON。

const GLB_PATH := "res://assets/player-rigged.glb"
const MOTION_PATH := "res://data/motion_input.json"
const RigDriverScript := preload("res://scenes/rig_driver.gd")


class Driver:
	extends Node

	var sk: Skeleton3D
	var drv
	var seq: Array = []
	var idx := 0
	var busy := false
	var frames: Array = []
	var neutral_start: Array = []

	func _v3(v: Vector3) -> Array:
		return [round(v.x * 1000000.0) / 1000000.0,
				round(v.y * 1000000.0) / 1000000.0,
				round(v.z * 1000000.0) / 1000000.0]

	func _q4(q: Quaternion) -> Array:
		return [round(q.w * 1000000.0) / 1000000.0,
				round(q.x * 1000000.0) / 1000000.0,
				round(q.y * 1000000.0) / 1000000.0,
				round(q.z * 1000000.0) / 1000000.0]

	func _neutral_pose() -> Array:
		var i := sk.find_bone("neutral_bone")
		if i < 0:
			return []
		return _q4(sk.get_bone_pose_rotation(i)) + \
			_v3(sk.get_bone_pose_position(i)) + \
			_v3(sk.get_bone_pose_scale(i))

	func _process(_delta: float) -> void:
		if busy:
			return
		if idx >= seq.size():
			busy = true
			var out := {
				"bone_count": sk.get_bone_count(),
				"bones": drv.bone_names,
				"frames_applied": drv.frame_count_applied,
				"frame_count": frames.size(),
				"neutral_start": neutral_start,
				"neutral_end": _neutral_pose(),
				"frames": frames,
			}
			print("DRIVE_JSON " + JSON.stringify(out))
			get_tree().quit(0)
			return
		busy = true
		var card := String(seq[idx][0])
		var f := int(seq[idx][1])
		var r = drv.apply_frame(card, f)
		# 等真实帧渲染，骨骼 global pose 才会刷新。
		await RenderingServer.frame_post_draw
		var engine_origin := {}
		var pose_readback := {}
		for n in drv.bone_names:
			var key := String(n)
			var i: int = drv.bone_idx[key]
			engine_origin[key] = _v3(sk.get_bone_global_pose(i).origin)
			pose_readback[key] = _q4(sk.get_bone_pose_rotation(i)) + \
				_v3(sk.get_bone_pose_position(i))
		frames.append({
			"card": card, "frame": f,
			"root_m": r["root_m"],
			"delta_deg": r["delta_deg"],
			"calc_global_origin": r["calc_global_origin"],
			"engine_global_origin": engine_origin,
			"pose_readback": pose_readback,
		})
		idx += 1
		busy = false


func _find_skel(n: Node) -> Skeleton3D:
	if n is Skeleton3D:
		return n as Skeleton3D
	for c in n.get_children():
		var r := _find_skel(c)
		if r != null:
			return r
	return null


func _build_stage() -> Camera3D:
	var we := WorldEnvironment.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.075, 0.090, 0.125)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.42, 0.48, 0.62)
	env.ambient_light_energy = 0.68
	we.environment = env
	root.add_child(we)
	var l := DirectionalLight3D.new()
	l.rotation_degrees = Vector3(-38.0, -32.0, 0.0)
	l.light_energy = 1.9
	root.add_child(l)
	var cam := Camera3D.new()
	cam.current = true
	cam.position = Vector3(0.0, 1.12, 3.55)
	cam.fov = 33.0
	cam.look_at(Vector3(0.0, 0.86, 0.0), Vector3.UP)
	root.add_child(cam)
	return cam


func _init() -> void:
	var glb := load(GLB_PATH)
	var mf := FileAccess.open(MOTION_PATH, FileAccess.READ)
	if glb == null or mf == null:
		print("DRIVE_JSON " + JSON.stringify({"error": "resource load failed"}))
		quit(1)
		return
	var motion: Dictionary = JSON.parse_string(mf.get_as_text())
	mf.close()
	var inst := (glb as PackedScene).instantiate()
	root.add_child(inst)
	var sk := _find_skel(inst)
	if sk == null:
		print("DRIVE_JSON " + JSON.stringify({"error": "skeleton missing"}))
		quit(1)
		return
	var drv := RigDriverScript.new()
	if not drv.setup(sk, motion):
		print("DRIVE_JSON " + JSON.stringify({"error": "RigDriver.setup failed"}))
		quit(1)
		return
	_build_stage()

	var seq: Array = [["stance", 0]]
	for card in ["jab", "cross", "wave"]:
		var n: int = motion["cards"][card]["frames"]
		for f in range(n):
			seq.append([card, f])

	var d := Driver.new()
	d.sk = sk
	d.drv = drv
	d.seq = seq
	d.neutral_start = d._neutral_pose()
	root.add_child(d)
	print("DRIVE_START frames=%d" % seq.size())
