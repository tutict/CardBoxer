extends Node2D
## G 路线：把 F 路线的 14 骨运行时驱动层接进 2D 擂台。
##
## 一个透明 SubViewport 里装 player-rigged.glb + 相机 + 灯，
## 用 ViewportTexture 画进 2D 画布；RigDriver 按 73 帧运动表现算 13 骨 pose。
## 本层**只画**，不改 position / HP / 伤害 / 牌型 / 硬直 / 阶段时长。
##
## 开关在 arena.gd：CARD_BOXER_3D 环境变量非空才创建本层，默认关。
## 对手侧仍是既有 2D 自绘（F 路线只有玩家侧带 skin 的 GLB），见验证记录边界。

const RigDriverScript := preload("res://scripts/rig_driver.gd")
const GLB_PATH := "res://assets/3d/player-rigged.glb"

const SV_W := 420
const SV_H := 520
# SubViewport 内部按 420x520 渲染保证清晰，贴回 2D 时按 2D 角色身高缩放。
# 2D 角色 head=-172 / foot=0，3D 人物在视口里约占 450/560 高。
const DRAW_SCALE := 0.45
const DRAW_OFFSET_X := 0.0
# 3D 人物脚在 SubViewport 里略高于底边；照原样贴会离 2D 影子约 27px，
# 看图后把整块下移，让脚落到擂台地面上。
const DRAW_OFFSET_Y := 18.0

var sv: SubViewport = null
var drv = null
var motion: Dictionary = {}
var ready_ok := false
var tex_drawn := false
var frames_applied := 0
var last_card := "stance"
var last_frame := 0


func _find_skel(n: Node) -> Skeleton3D:
	if n is Skeleton3D:
		return n as Skeleton3D
	for c in n.get_children():
		var r := _find_skel(c)
		if r != null:
			return r
	return null


func _add_light(rot: Vector3, energy: float, col: Color, shadow: bool) -> void:
	var l := DirectionalLight3D.new()
	l.rotation_degrees = rot
	l.light_energy = energy
	l.light_color = col
	l.shadow_enabled = shadow
	sv.add_child(l)


func setup(p_motion: Dictionary) -> bool:
	motion = p_motion
	if motion.is_empty():
		return false

	sv = SubViewport.new()
	sv.size = Vector2i(SV_W, SV_H)
	sv.transparent_bg = true
	sv.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	sv.disable_3d = false
	add_child(sv)

	var res := load(GLB_PATH)
	if res == null or not (res is PackedScene):
		return false
	var inst: Node3D = (res as PackedScene).instantiate()
	sv.add_child(inst)

	var skel := _find_skel(inst)
	if skel == null:
		return false
	drv = RigDriverScript.new()
	if not drv.setup(skel, motion):
		return false

	var cam := Camera3D.new()
	cam.current = true
	cam.fov = 33.0
	cam.near = 0.05
	cam.far = 100.0
	cam.position = Vector3(0.0, 1.12, 3.55)
	sv.add_child(cam)
	cam.look_at(Vector3(0.0, 0.86, 0.0), Vector3.UP)

	# 不加 Ground：2D 背景已有擂台地面，透明视口让背景透出来。
	_add_light(Vector3(-38.0, -32.0, 0.0), 1.9,
			Color(1.00, 0.96, 0.90), true)
	_add_light(Vector3(-20.0, 145.0, 0.0), 0.75,
			Color(0.68, 0.79, 1.00), false)
	_add_light(Vector3(-12.0, 75.0, 0.0), 0.55,
			Color(1.00, 0.85, 0.70), false)
	_add_light(Vector3(-25.0, 200.0, 0.0), 0.95,
			Color(0.76, 0.85, 1.00), false)

	apply("stance", 0)
	ready_ok = true
	return true


## card 只认 73 帧表里的三档；其余（含平局 ""）一律 stance。
func apply(card: String, frame: int) -> void:
	if drv == null:
		return
	var c := card
	if c != "jab" and c != "cross" and c != "wave":
		c = "stance"
	var f := 0
	if c != "stance":
		var n := int(motion["cards"][c]["frames"])
		f = clampi(frame, 0, maxi(0, n - 1))
	last_card = c
	last_frame = f
	drv.apply_frame(c, f)
	frames_applied += 1


func _draw() -> void:
	if sv == null:
		return
	var t := sv.get_texture()
	if t == null:
		return
	var w := float(SV_W) * DRAW_SCALE
	var h := float(SV_H) * DRAW_SCALE
	draw_texture_rect(t, Rect2(DRAW_OFFSET_X - w * 0.5,
			-h + DRAW_OFFSET_Y, w, h), false)
	tex_drawn = true


func _process(_d: float) -> void:
	if ready_ok:
		queue_redraw()
