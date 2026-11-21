extends SceneTree
## G 路线 P0 技术探针：GL Compatibility 下，2D 主视口能否显示 3D SubViewport。
##
## 跑法（必须带窗口，headless dummy driver 不发 frame_post_draw）：
##   G_SHOT_DIR=<abs> godot --path <probe_project_g> --resolution 1280x720 \
##     --script res://probes/probe_subviewport.gd --quit-after 6000
##
## 验证三件事：① 2D 绘制链正常（背景 + 网格 + 左侧色块）；
## ② SubViewport 里 3D GLB 能被 ViewportTexture 取到并画进 2D；
## ③ 整张 1280x720 能截下来且 3D 区域非空白。
## 不写工程内任何文件，不碰可运行游戏工程。

const GLB_PATH := "res://assets/player-rigged.glb"


class Canvas2D:
	extends Node2D

	const VIEW_POS := Vector2(340.0, 80.0)
	const VIEW_SIZE := Vector2(600.0, 560.0)
	const BG := Color(0.075, 0.090, 0.125)

	var sv: SubViewport = null
	var draw_count := 0
	var tex_ok := false

	func _draw() -> void:
		draw_count += 1
		draw_rect(Rect2(0.0, 0.0, 1280.0, 720.0), BG)
		for x in range(0, 1281, 160):
			draw_line(Vector2(x, 0), Vector2(x, 720),
					Color(0.18, 0.24, 0.33), 1.0)
		for y in range(0, 721, 120):
			draw_line(Vector2(0, y), Vector2(1280, y),
					Color(0.18, 0.24, 0.33), 1.0)
		# 左侧色块：2D 绘制链的可见锚点，与 3D 区域分开。
		draw_rect(Rect2(40.0, 120.0, 180.0, 420.0), Color(0.55, 0.18, 0.22))
		if sv != null:
			var t := sv.get_texture()
			if t != null:
				draw_texture_rect(t, Rect2(VIEW_POS, VIEW_SIZE), false)
				tex_ok = true

	func _process(_d: float) -> void:
		queue_redraw()


class Shot:
	extends Node

	const SETTLE := 10

	var canvas: Node2D
	var sv: SubViewport
	var out_dir := ""
	var done := false

	func _process(_d: float) -> void:
		if done:
			return
		done = true
		# 4096² 贴图首帧可能还没上传完，多等几帧再抓。
		for _i in range(SETTLE):
			await RenderingServer.frame_post_draw
		var img := get_viewport().get_texture().get_image()
		var path := out_dir + "/sv-probe.png"
		var err := img.save_png(path)
		var info := {
			"path": path,
			"w": img.get_width(), "h": img.get_height(),
			"save_error": int(err),
			"draw_count": int(canvas.get("draw_count")),
			"tex_ok": bool(canvas.get("tex_ok")),
			"sv_size": [sv.size.x, sv.size.y],
			"sv_transparent": sv.transparent_bg,
			"sv_children": sv.get_child_count(),
		}
		print("SV_JSON " + JSON.stringify(info))
		get_tree().quit(0)


func _add_light(sv: SubViewport, rot: Vector3, energy: float,
		col: Color, shadow: bool) -> void:
	var l := DirectionalLight3D.new()
	l.rotation_degrees = rot
	l.light_energy = energy
	l.light_color = col
	l.shadow_enabled = shadow
	sv.add_child(l)


func _init() -> void:
	var out_dir := OS.get_environment("G_SHOT_DIR")
	if out_dir == "":
		print("SV_JSON " + JSON.stringify({"error": "G_SHOT_DIR missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)

	var canvas := Canvas2D.new()
	root.add_child(canvas)

	var sv := SubViewport.new()
	sv.size = Vector2i(600, 560)
	sv.transparent_bg = true
	sv.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	sv.disable_3d = false
	canvas.add_child(sv)
	canvas.set("sv", sv)

	var res := load(GLB_PATH)
	if res == null or not (res is PackedScene):
		print("SV_JSON " + JSON.stringify(
				{"error": "glb load failed", "path": GLB_PATH}))
		quit(1)
		return
	var inst: Node3D = (res as PackedScene).instantiate()
	sv.add_child(inst)

	var cam := Camera3D.new()
	cam.current = true
	cam.fov = 33.0
	cam.near = 0.05
	cam.far = 100.0
	cam.position = Vector3(0.0, 1.12, 3.55)
	sv.add_child(cam)
	cam.look_at(Vector3(0.0, 0.86, 0.0), Vector3.UP)

	_add_light(sv, Vector3(-38.0, -32.0, 0.0), 1.9,
			Color(1.00, 0.96, 0.90), true)
	_add_light(sv, Vector3(-20.0, 145.0, 0.0), 0.75,
			Color(0.68, 0.79, 1.00), false)
	_add_light(sv, Vector3(-12.0, 75.0, 0.0), 0.55,
			Color(1.00, 0.85, 0.70), false)
	_add_light(sv, Vector3(-25.0, 200.0, 0.0), 0.95,
			Color(0.76, 0.85, 1.00), false)

	var s := Shot.new()
	s.canvas = canvas
	s.sv = sv
	s.out_dir = out_dir
	root.add_child(s)
	print("SV_START glb=%s sv=%dx%d" % [GLB_PATH, sv.size.x, sv.size.y])
