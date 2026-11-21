extends SceneTree
## 阶段 5：引擎内多帧截帧 —— 证明「骨骼数值动了」真的变成了「像素动了」。
##
## 加载 project.godot 的 main_scene（player_driven.tscn），关掉 auto_play，
## 逐帧由同一个 RigDriver 驱动并抓帧；「用户 F5 打开能看见」与
## 「自动截图」走同一条场景链，不是两套口径。
##
## 帧表刻意含 stance 两次（repeat，确定性判据）与两种 yaw（体积判据）。
## 不能 --headless：dummy driver 不发 RenderingServer.frame_post_draw。
##
## 用法：F_SHOT_DIR=<abs> godot --path <proj> --resolution 900x1100 \
##         --script res://probes/render_driven.gd --quit-after 30000

const SCENE_PATH := "res://scenes/player_driven.tscn"

# name, seq_index, camera_yaw_deg
const SHOTS := [
	{"name": "stance-front",        "seq": 0,  "yaw": 0.0},
	{"name": "stance-front-repeat", "seq": 0,  "yaw": 0.0},
	{"name": "jab06-front",         "seq": 7,  "yaw": 0.0},
	{"name": "cross07-front",       "seq": 22, "yaw": 0.0},
	{"name": "wave17-front",        "seq": 54, "yaw": 0.0},
	{"name": "wave35-front",        "seq": 72, "yaw": 0.0},
	{"name": "jab06-angle35",       "seq": 7,  "yaw": 35.0},
	{"name": "cross07-angle35",     "seq": 22, "yaw": 35.0},
	{"name": "wave17-angle35",      "seq": 54, "yaw": 35.0},
]


class Driver:
	extends Node
	const SETTLE := 5

	var stage: Node3D
	var cam: Camera3D
	var shots: Array = []
	var out_dir := ""
	var idx := 0
	var busy := false
	var checked := false
	var report: Array = []

	func _place(yaw_deg: float) -> void:
		var yaw := deg_to_rad(yaw_deg)
		var r := 3.55
		cam.position = Vector3(r * sin(yaw), 1.12, r * cos(yaw))
		cam.fov = 33.0
		cam.look_at(Vector3(0.0, 0.86, 0.0), Vector3.UP)

	func _process(_delta: float) -> void:
		if busy:
			return
		if idx >= shots.size():
			busy = true
			print("RENDER_JSON " + JSON.stringify({"shots": report,
					"stage_ready": stage.get("ready_ok"),
					"frames_applied": stage.get("frames_applied")}))
			get_tree().quit(0)
			return
		busy = true
		var s: Dictionary = shots[idx]
		# _init() 里 add_child 后子场景 _ready() 还没跑，必须抓帧前复核。
		if not checked:
			for _i in range(SETTLE):
				await RenderingServer.frame_post_draw
			checked = true
			if not bool(stage.get("ready_ok")):
				print("STAGE_NOT_READY")
				get_tree().quit(1)
				return
		stage.set("auto_play", false)
		_place(float(s["yaw"]))
		var r: Dictionary = stage.call("apply", int(s["seq"]))
		for _i in range(SETTLE):
			await RenderingServer.frame_post_draw
		var img := get_viewport().get_texture().get_image()
		var path := "%s/f-%s.png" % [out_dir, String(s["name"])]
		var err := img.save_png(path)
		report.append({
			"name": String(s["name"]), "seq": int(s["seq"]),
			"yaw": float(s["yaw"]),
			"card": r.get("card", ""), "frame": r.get("frame", -1),
			"root_m": r.get("root_m", []),
			"delta_deg": r.get("delta_deg", {}),
			"path": path, "w": img.get_width(), "h": img.get_height(),
			"save_error": int(err),
		})
		idx += 1
		busy = false


func _init() -> void:
	var shot_dir := OS.get_environment("F_SHOT_DIR")
	if shot_dir == "":
		print("RENDER_JSON " + JSON.stringify({"error": "F_SHOT_DIR missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(shot_dir)
	var res := load(SCENE_PATH)
	if res == null or not (res is PackedScene):
		print("RENDER_JSON " + JSON.stringify({"error": "main_scene load failed"}))
		quit(1)
		return
	var inst: Node3D = (res as PackedScene).instantiate()
	inst.set("auto_play", false)
	root.add_child(inst)
	var cam := inst.get_node_or_null("Camera3D") as Camera3D
	if cam == null:
		print("RENDER_JSON " + JSON.stringify({"error": "camera missing"}))
		quit(1)
		return
	var d := Driver.new()
	d.stage = inst
	d.cam = cam
	d.shots = SHOTS
	d.out_dir = shot_dir
	root.add_child(d)
	print("RENDER_START shots=%d out=%s" % [SHOTS.size(), shot_dir])
