extends SceneTree
## D 路线：Godot 4.5 **引擎内** 3D 截帧，供 Creative Review 看图。
##
## 跑法（必须带窗口）：
##   D_SHOT_DIR=<abs> D_VIEWS=front,back godot --path <probe_project_d> \
##     --resolution 900x1100 --script res://probes/render_3d.gd --quit-after 6000
## 不能加 --headless：dummy driver 不发 RenderingServer.frame_post_draw，
## 本脚本会永远等不到帧（外观层 capture_skin.py 已实测过）。
##
## 只 load 一份 foe-full.glb，搭最小棚拍场景，逐视角存 PNG；
## 不写工程内任何文件，不碰可运行游戏工程。

const GLB_PATH := "res://assets/foe-full.glb"

# yaw 为绕 +Y 的角度；相机始终 look_at 目标点。半径/高度单位米。
# 网格 AABB 实测 x[-0.608,0.608] y[0,1.72] z[-0.360,0.360]。
# v2：第一版 radius=3.20/fov=34 让人物顶到上下边缘，背面在全暗里几乎
# 读不出披风；拉远到 3.55 并补一盏固定背光（六视角同一套灯，口径公平）。
const VIEWS := [
	{"name": "front",   "yaw": 0.0,   "radius": 3.55, "height": 1.12, "fov": 33.0, "ty": 0.86},
	{"name": "angle35", "yaw": 35.0,  "radius": 3.55, "height": 1.12, "fov": 33.0, "ty": 0.86},
	{"name": "side90",  "yaw": 90.0,  "radius": 3.55, "height": 1.12, "fov": 33.0, "ty": 0.86},
	{"name": "back",    "yaw": 180.0, "radius": 3.55, "height": 1.12, "fov": 33.0, "ty": 0.86},
	{"name": "upper",   "yaw": 20.0,  "radius": 1.70, "height": 1.60, "fov": 32.0, "ty": 1.38},
	{"name": "wide",    "yaw": 15.0,  "radius": 4.80, "height": 1.60, "fov": 38.0, "ty": 0.88},
]


class Driver:
	extends Node
	const SETTLE := 4

	var cam: Camera3D
	var views: Array = []
	var out_dir := ""
	var idx := 0
	var busy := false
	var report: Array = []

	func _place(v: Dictionary) -> void:
		var yaw := deg_to_rad(float(v["yaw"]))
		var r := float(v["radius"])
		cam.position = Vector3(r * sin(yaw), float(v["height"]), r * cos(yaw))
		cam.fov = float(v["fov"])
		cam.look_at(Vector3(0.0, float(v["ty"]), 0.0), Vector3.UP)

	func _process(_delta: float) -> void:
		if busy:
			return
		if idx >= views.size():
			busy = true
			print("RENDER_JSON " + JSON.stringify({"views": report}))
			get_tree().quit(0)
			return
		busy = true
		var v: Dictionary = views[idx]
		_place(v)
		# 4096² 贴图首帧可能还没上传完，多等几帧再抓，避免抓到空白/未贴图。
		for _i in range(SETTLE):
			await RenderingServer.frame_post_draw
		var img := get_viewport().get_texture().get_image()
		var path := "%s/godot-%s.png" % [out_dir, String(v["name"])]
		var err := img.save_png(path)
		report.append({
			"name": String(v["name"]), "yaw": float(v["yaw"]),
			"radius": float(v["radius"]), "fov": float(v["fov"]),
			"path": path, "w": img.get_width(), "h": img.get_height(),
			"save_error": int(err),
		})
		idx += 1
		busy = false


func _add_light(rot: Vector3, energy: float, col: Color, shadow: bool) -> void:
	var l := DirectionalLight3D.new()
	l.rotation_degrees = rot
	l.light_energy = energy
	l.light_color = col
	l.shadow_enabled = shadow
	root.add_child(l)


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

	_add_light(Vector3(-38.0, -32.0, 0.0), 1.9,
			Color(1.00, 0.96, 0.90), true)
	_add_light(Vector3(-20.0, 145.0, 0.0), 0.75,
			Color(0.68, 0.79, 1.00), false)
	_add_light(Vector3(-12.0, 75.0, 0.0), 0.55,
			Color(1.00, 0.85, 0.70), false)
	# 固定背光：第一版 back 视角披风全黑，读不出结构。
	_add_light(Vector3(-25.0, 200.0, 0.0), 0.95,
			Color(0.76, 0.85, 1.00), false)

	var ground := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(12.0, 12.0)
	ground.mesh = plane
	var gmat := StandardMaterial3D.new()
	gmat.albedo_color = Color(0.10, 0.12, 0.16)
	gmat.roughness = 0.95
	ground.material_override = gmat
	ground.position = Vector3(0.0, -0.012, 0.0)
	root.add_child(ground)

	var cam := Camera3D.new()
	cam.current = true
	cam.near = 0.05
	cam.far = 100.0
	root.add_child(cam)
	return cam


func _init() -> void:
	var shot_dir := OS.get_environment("D_SHOT_DIR")
	if shot_dir == "":
		print("RENDER_JSON " + JSON.stringify({"error": "D_SHOT_DIR missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(shot_dir)

	var names := OS.get_environment("D_VIEWS")
	var wanted: PackedStringArray = names.split(",", false)
	var selected: Array = []
	for entry in VIEWS:
		var v: Dictionary = entry
		if wanted.is_empty() or wanted.has(String(v["name"])):
			selected.append(v)
	if selected.is_empty():
		print("RENDER_JSON " + JSON.stringify({"error": "no view selected"}))
		quit(1)
		return

	var res := load(GLB_PATH)
	if res == null or not (res is PackedScene):
		print("RENDER_JSON " + JSON.stringify({"error": "glb load failed",
				"path": GLB_PATH}))
		quit(1)
		return
	var inst: Node3D = (res as PackedScene).instantiate()
	root.add_child(inst)

	var cam := _build_stage()
	var d := Driver.new()
	d.cam = cam
	d.views = selected
	d.out_dir = shot_dir
	root.add_child(d)
	print("RENDER_START views=%d out=%s" % [selected.size(), shot_dir])
