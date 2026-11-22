extends Node3D
## F 路线主场景：打开工程（F5）就能看到女角色循环播放三档攻击。
##
## 驱动只依赖 res://data/motion_input.json 的原始 2D 关节表；
## 不加载任何烘死的动画/pose。RigDriver 是 GDScript 运行时现算的
## 14 骨驱动层，见 scenes/rig_driver.gd。
##
## 渲染探针会把 auto_play 关掉后自己逐帧驱动并截帧，
## 保证「打开能看见」与「自动截图」走的是同一条场景链。

const MOTION_PATH := "res://data/motion_input.json"
const PLAY_FPS := 12.0
# 不用 class_name 全局注册：--script 启动路径不扫全局类缓存，
# 用 preload 与 probes/probe_drive.gd 保持同一口径。
const RigDriverScript := preload("res://scenes/rig_driver.gd")

@export var auto_play: bool = true

var drv
var skel: Skeleton3D
var seq: Array = []
var play_index: int = 0
var frames_applied: int = 0
var ready_ok: bool = false

var _acc := 0.0


func _find_skel(n: Node) -> Skeleton3D:
	if n is Skeleton3D:
		return n as Skeleton3D
	for c in n.get_children():
		var r := _find_skel(c)
		if r != null:
			return r
	return null


func _build_stage() -> void:
	var we := WorldEnvironment.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.075, 0.090, 0.125)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.42, 0.48, 0.62)
	env.ambient_light_energy = 0.68
	we.environment = env
	add_child(we)
	var ground := get_node_or_null("Ground") as MeshInstance3D
	if ground != null:
		var plane := PlaneMesh.new()
		plane.size = Vector2(12.0, 12.0)
		ground.mesh = plane
		var mat := StandardMaterial3D.new()
		mat.albedo_color = Color(0.10, 0.12, 0.16)
		mat.roughness = 0.95
		ground.material_override = mat


func _ready() -> void:
	_build_stage()
	var mf := FileAccess.open(MOTION_PATH, FileAccess.READ)
	if mf == null:
		push_error("F: motion_input.json missing")
		return
	var motion: Dictionary = JSON.parse_string(mf.get_as_text())
	mf.close()
	skel = _find_skel(self)
	if skel == null:
		push_error("F: Skeleton3D missing")
		return
	drv = RigDriverScript.new()
	if not drv.setup(skel, motion):
		push_error("F: RigDriver.setup failed")
		return
	seq = [["stance", 0]]
	for card in ["jab", "cross", "wave"]:
		var n: int = motion["cards"][card]["frames"]
		for f in range(n):
			seq.append([card, f])
	apply(0)
	ready_ok = true
	print("F_READY bones=%d frames=%d auto_play=%s" %
			[skel.get_bone_count(), seq.size(), str(auto_play)])


func apply(index: int) -> Dictionary:
	if drv == null or seq.is_empty():
		return {}
	var i := index % seq.size()
	play_index = i
	var r: Dictionary = drv.apply_frame(String(seq[i][0]), int(seq[i][1]))
	frames_applied += 1
	return r


func _process(delta: float) -> void:
	if not auto_play or not ready_ok:
		return
	_acc += delta
	var step := 1.0 / PLAY_FPS
	while _acc >= step:
		_acc -= step
		apply(play_index + 1)
