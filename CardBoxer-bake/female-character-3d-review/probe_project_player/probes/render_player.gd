extends SceneTree
## Godot 4.5 引擎内女角色 3D 截帧。
##
## 跑法（必须带窗口，--headless 的 dummy driver 不发 frame_post_draw）：
##   P_SHOT_DIR=<abs> P_VIEWS=front,back godot --path <probe_project_player> \
##     --resolution 900x1100 --script res://probes/render_player.gd --quit-after 6000
##
## 这里加载的是 project.godot 的 main_scene（player_showcase.tscn），
## 所以「用户双击打开能看见」和「自动截图」走的是同一条场景链。

const SCENE_PATH := "res://scenes/player_showcase.tscn"

const VIEWS := [
	{"name": "front",   "yaw": 0.0,   "radius": 3.55, "height": 1.12, "fov": 33.0, "ty": 0.86},
	{"name": "angle35", "yaw": 35.0,  "radius": 3.55, "height": 1.12, "fov": 33.0, "ty": 0.86},
	{"name": "side90",  "yaw": 90.0,  "radius": 3.55, "height": 1.12, "fov": 33.0, "ty": 0.86},
	{"name": "back",    "yaw": 180.0, "radius": 3.55, "height": 1.12, "fov": 33.0, "ty": 0.86},
]


class Driver:
	extends Node
	const SETTLE := 4

	var cam: Camera3D
	var stage: Node3D
	var views: Array = []
	var out_dir := ""
	var idx := 0
	var busy := false
	var checked := false
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
		for _i in range(SETTLE):
			await RenderingServer.frame_post_draw
		# _init() 里 _ready() 还没跑（日志实测 SCENE_LOADED 早于
		# SHOWCASE_READY），可见性必须在真正抓帧前复核一次。
		if not checked:
			checked = true
			var hs := 0
			var hp := 0
			for m in stage.find_children("*", "MeshInstance3D", true, false):
				var mi := m as MeshInstance3D
				if String(mi.name) == "e_continuous_shell" and not mi.visible:
					hs += 1
				if String(mi.name) == "node_0" and mi.visible:
					hp += 1
			print("FRAME_VISIBILITY hidden_proxy_shell=" + str(hs) +
					" visible_highpoly=" + str(hp))
		var img := get_viewport().get_texture().get_image()
		var path := "%s/godot-player-%s.png" % [out_dir, String(v["name"])]
		var err := img.save_png(path)
		report.append({
			"name": String(v["name"]), "yaw": float(v["yaw"]),
			"radius": float(v["radius"]), "fov": float(v["fov"]),
			"path": path, "w": img.get_width(), "h": img.get_height(),
			"save_error": int(err),
		})
		idx += 1
		busy = false


func _init() -> void:
	var shot_dir := OS.get_environment("P_SHOT_DIR")
	if shot_dir == "":
		print("RENDER_JSON " + JSON.stringify({"error": "P_SHOT_DIR missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(shot_dir)

	var names := OS.get_environment("P_VIEWS")
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

	var res := load(SCENE_PATH)
	if res == null or not (res is PackedScene):
		print("RENDER_JSON " + JSON.stringify({"error": "main_scene load failed",
				"path": SCENE_PATH}))
		quit(1)
		return
	var inst: Node3D = (res as PackedScene).instantiate()
	root.add_child(inst)

	var hidden_shell := 0
	var highpoly := 0
	for m in inst.find_children("*", "MeshInstance3D", true, false):
		var mi := m as MeshInstance3D
		if String(mi.name) == "e_continuous_shell" and not mi.visible:
			hidden_shell += 1
		if String(mi.name) == "node_0" and mi.visible:
			highpoly += 1
	print("SCENE_LOADED hidden_proxy_shell=" + str(hidden_shell) +
			" visible_highpoly=" + str(highpoly))

	var cam := inst.get_node_or_null("Camera3D") as Camera3D
	if cam == null:
		print("RENDER_JSON " + JSON.stringify({"error": "camera missing"}))
		quit(1)
		return

	var d := Driver.new()
	d.cam = cam
	d.stage = inst
	d.views = selected
	d.out_dir = shot_dir
	root.add_child(d)
	print("RENDER_START views=%d out=%s hidden_shell=%d highpoly=%d" %
			[selected.size(), shot_dir, hidden_shell, highpoly])
