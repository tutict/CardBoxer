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
# H 路线：对手怪是另一份带 skin 的 GLB（13 骨同名、rest 更矮更宽）。
const FOE_GLB_PATH := "res://assets/3d/foe-rigged.glb"

const SV_W := 420
const SV_H := 520
# SubViewport 内部按 420x520 渲染保证清晰，贴回 2D 时按 2D 角色身高缩放。
# 2D 角色 head=-172 / foot=0，3D 人物在视口里约占 450/560 高。
const DRAW_SCALE := 0.45
const DRAW_OFFSET_X := 0.0
# 3D 人物脚在 SubViewport 里略高于底边；照原样贴会离 2D 影子约 27px，
# 看图后把整块下移，让脚落到擂台地面上。
const DRAW_OFFSET_Y := 18.0

# ── G 路线「侧面战斗」表现层 ──────────────────────────────────
# 只改观察方向，不改 rig_driver 的任何一根骨头 / 任何一条公式。
# 相机绕 +Y 转 yaw（3/4 侧身）；贴图可选水平镜像让脸朝对手。
# D 路线实测 yaw=90° 时零厚度披风壳退化成一条细线，且骨架动作平面
# (XY) 与视线平行会让出拳幅度被压成 0，所以定稿角度必须 < 70°。
const CAM_RADIUS := 3.55
const CAM_HEIGHT := 1.12
const CAM_TARGET_Y := 0.86
# 2026-11-14 订正：G/H 路线原注释把方向写反了。
# 原话「+55° = 相机在角色左前方，脸朝画面右」与实测相反：
# 同进程扫描（朝向修复/shots/o-*.png）逐格看图，+55° 看到的是角色
# 左后侧，脸朝画面左、黑披风在右；-55° 才脸朝画面右、披风在左后。
# 玩家站左侧、对手站右侧，要面对面就必须：玩家 -55°（朝右）、
# 对手 +55°（朝左）。原来 +55/-55 让两人背对背朝外，用户反馈属实。
# 不用 ±90°：D 路线实测零厚度披风壳会退化成一条线，且骨架动作平面
# (XY) 与视线平行后出拳幅度被压成 0。
const DEFAULT_SIDE_YAW := -55.0
const DEFAULT_SIDE_FLIP := false
# H 路线原文「对手 yaw 取负」同属写反；取正才让右侧对手脸朝左。
# arena.gd 与所有探针都引用本常量，改这一处即可同步。
const DEFAULT_FOE_YAW := 55.0

# ── I 路线「视觉区分度」：只作用于 foe ──────────────────────
# rootcause_i.json：贴图 UV 岛亮度差 70.99 被四盏高强度灯 +
# metallic 乘数 1.0 吃成渲染 -11.18。定稿走纯 2D 合成层：
# 3D 渲染树（灯 / 材质 / mesh）与 GLB 一个都不动。
# 数值与 data/visual_diff_spec.json 逐项对应，改一处要改两处。
# 已退役：3D albedo tint、metallic 乘数（v2 串扰玩家层 7940 px）、
# 灯能量缩放（v1 跨 SubViewport 串光）；负结果见 data/v1-failed/
# 与 data/v2-failed/。shader 字符串是 tint 的唯一真相来源。
const FOE_CANVAS_SHADER_CODE := "shader_type canvas_item;\nvoid fragment() {\n\tvec4 c = texture(TEXTURE, UV);\n\tCOLOR = vec4(c.rgb * vec3(0.42, 0.30, 0.28), c.a);\n}\n"
const FOE_DRAW_SCALE_X := 1.22
const FOE_DRAW_SCALE_Y := 0.94

# 定稿站架（看图证据 boards/G-侧身站架反向扫描.png 的 r0-flip-all）：
# 双拳收到胸前护脸、前后脚分开、双脚贴地、无撕裂。
# 单位 = 度，绕 Z，与 rig_driver 的 delta 同符号口径。
# 这只是表现层静态偏置：rig_driver / motion_input / 73 帧表一字未改。
const DEFAULT_STANCE_BIAS := {
	"upperarm_f": 26.0, "forearm_f": -50.0,
	"upperarm_b": -26.0, "forearm_b": 50.0,
	"spine": 4.0, "head": -2.4,
	"thigh_f": 10.0, "shin_f": -6.0,
	"thigh_b": -12.0, "shin_b": 7.0,
}

var sv: SubViewport = null
var cam: Camera3D = null
var drv = null
var motion: Dictionary = {}
# H 路线：同一个层类服务两个角色；默认仍是 G 的玩家形态。
var glb_path := GLB_PATH
var role_id := "player"
var ready_ok := false
var tex_drawn := false
var frames_applied := 0
var last_card := "stance"
var last_frame := 0
var view_yaw_deg := DEFAULT_SIDE_YAW
var view_flip := DEFAULT_SIDE_FLIP
var view_changes := 0
# I 路线：foe 专属视觉开关。_mesh_rows/_light_rows 仅供诊断读回；
# _foe_materials 恒空（v3 断言没有 3D 材质副本）；_foe_canvas_mat
# 是本层本地的 2D 合成材质，物理上不会串到玩家层。
var foe_visual := false
var _mesh_rows: Array = []
var _light_rows: Array = []
var _foe_materials: Array = []
var _foe_canvas_mat: ShaderMaterial = null
# 格斗站架偏置（度，绕 Z，与 rig_driver 同符号口径）。
# 这是表现层后处理，不改 rig_driver 的公式 / motion_input / 73 帧表。
# 可用 CARD_BOXER_3D_STANCE=none 关掉，用来做「有/无站架」A/B 取证。
var stance_bias_deg: Dictionary = DEFAULT_STANCE_BIAS.duplicate()


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
	# I 路线：记下原始能量/颜色，set_foe_visual(false) 要逐项还原。
	_light_rows.append({"light": l, "energy": energy,
			"color": col})


## H 路线：在 setup() 之前指定角色资产与朝向。
## 不传 = G 路线原样（玩家 / player-rigged.glb / +55° / 不翻）。
func configure(p_role: String, p_glb: String, p_yaw: float,
		p_flip: bool) -> void:
	role_id = p_role
	glb_path = p_glb
	view_yaw_deg = p_yaw
	view_flip = p_flip
	# I 路线：只有 foe 启用视觉区分；none 用于同进程 A/B 还原 H 原样。
	if p_role == "foe" and OS.get_environment(
			"CARD_BOXER_FOE_VISUAL") != "none":
		foe_visual = true


## 探针/运行时改视角；不动骨架，只摆相机 + 决定贴图是否镜像。
func set_view(p_yaw_deg: float, p_flip: bool) -> void:
	view_yaw_deg = p_yaw_deg
	view_flip = p_flip
	view_changes += 1
	_place_camera()
	queue_redraw()


func _place_camera() -> void:
	if cam == null:
		return
	var a := deg_to_rad(view_yaw_deg)
	cam.position = Vector3(CAM_RADIUS * sin(a), CAM_HEIGHT,
			CAM_RADIUS * cos(a))
	cam.look_at(Vector3(0.0, CAM_TARGET_Y, 0.0), Vector3.UP)


func setup(p_motion: Dictionary) -> bool:
	motion = p_motion
	if motion.is_empty():
		return false
	# 环境变量只用于玩家侧探针扫角度；对手侧由 configure() 定死朝向，
	# 避免玩家探针的环境变量把对手一起转了。
	if role_id == "player":
		var yaw_env := OS.get_environment("CARD_BOXER_3D_YAW")
		if yaw_env != "":
			view_yaw_deg = float(yaw_env)
		var flip_env := OS.get_environment("CARD_BOXER_3D_FLIP")
		if flip_env != "":
			view_flip = flip_env != "0"
	# none = 退回 F 路线原样 A-pose，只用于 A/B 取证，不是生产默认。
	if OS.get_environment("CARD_BOXER_3D_STANCE") == "none":
		stance_bias_deg = {}

	sv = SubViewport.new()
	sv.size = Vector2i(SV_W, SV_H)
	sv.transparent_bg = true
	sv.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	sv.disable_3d = false
	add_child(sv)

	var res := load(glb_path)
	if res == null or not (res is PackedScene):
		return false
	var inst: Node3D = (res as PackedScene).instantiate()
	sv.add_child(inst)
	# I 路线：收集 mesh / 灯初值，仅供 visual_state() 读回诊断；
	# v3 不复制、不改写任何 3D 材质。
	_collect_meshes(inst)

	var skel := _find_skel(inst)
	if skel == null:
		return false
	drv = RigDriverScript.new()
	if not drv.setup(skel, motion):
		return false

	cam = Camera3D.new()
	cam.current = true
	cam.fov = 33.0
	cam.near = 0.05
	cam.far = 100.0
	sv.add_child(cam)
	_place_camera()

	# 不加 Ground：2D 背景已有擂台地面，透明视口让背景透出来。
	_add_light(Vector3(-38.0, -32.0, 0.0), 1.9,
			Color(1.00, 0.96, 0.90), true)
	_add_light(Vector3(-20.0, 145.0, 0.0), 0.75,
			Color(0.68, 0.79, 1.00), false)
	_add_light(Vector3(-12.0, 75.0, 0.0), 0.55,
			Color(1.00, 0.85, 0.70), false)
	_add_light(Vector3(-25.0, 200.0, 0.0), 0.95,
			Color(0.76, 0.85, 1.00), false)

	if foe_visual:
		set_foe_visual(true)
	apply("stance", 0)
	ready_ok = true
	return true


## card 只认 73 帧表里的三档；其余（含平局 ""）一律 stance。
## 站架偏置只加在 driver 算完的 pose 上，逐帧重新叠加（driver 每帧都会
## 覆写全部 13 骨），因此不会累积、不会污染 retarget 公式。
func set_stance_bias(p_bias: Dictionary) -> void:
	stance_bias_deg = p_bias.duplicate()
	queue_redraw()


func _apply_stance_bias() -> void:
	if stance_bias_deg.is_empty() or drv == null or drv.skel == null:
		return
	for key in stance_bias_deg.keys():
		var n := String(key)
		if not drv.bone_idx.has(n):
			continue
		var i: int = int(drv.bone_idx[n])
		var cur: Quaternion = drv.skel.get_bone_pose_rotation(i)
		var q := Quaternion(Vector3(0.0, 0.0, 1.0),
				-deg_to_rad(float(stance_bias_deg[key])))
		drv.skel.set_bone_pose_rotation(i, cur * q)


## I 路线：递归收集 MeshInstance3D 的 surface 基础材质。
func _collect_meshes(n: Node) -> void:
	if n is MeshInstance3D:
		var mi := n as MeshInstance3D
		if mi.mesh != null:
			for i in range(mi.mesh.get_surface_count()):
				_mesh_rows.append({"mi": mi, "surface": i,
						"base": mi.mesh.surface_get_material(i)})
	for c in n.get_children():
		_collect_meshes(c)


## I 路线：可反复切换。true = 本层挂 canvas_item 调色 shader +
## 加宽压矮绘制尺寸；false = 清 material、尺寸回 1.0，逐项还原到
## H 路线原样（玩家层恒定 false，从不被本函数触碰）。
func set_foe_visual(enabled: bool) -> void:
	foe_visual = enabled
	# I 路线 v3：3D 材质一律不动。v2 实测改 foe 层 surface override
	# 会让玩家层角色整体变暗（7940 px / 变化像素平均 -25），即使两层
	# 灯能量、玩家层 override、玩家层 CanvasItem.material 全部恒定。
	# 视觉区分全部交给纯 2D 合成的 canvas_item shader + 绘制尺寸。
	# I 路线 v2：灯光一个都不碰。v1 实测 GL Compatibility 下改一个
	# SubViewport 的 DirectionalLight3D 会让另一个 SubViewport 的角色
	# 一起变暗（玩家层灯能量恒定，玩家 ROI 仍暗 20.08）。
	# 改用每层独立的 CanvasItem.material，物理上不会串到玩家层。
	if enabled:
		if _foe_canvas_mat == null:
			var sh := Shader.new()
			sh.code = FOE_CANVAS_SHADER_CODE
			var sm := ShaderMaterial.new()
			sm.shader = sh
			_foe_canvas_mat = sm
		material = _foe_canvas_mat
	else:
		material = null
	queue_redraw()


## 探针读回状态，避免靠画面猜开关有没有生效。
func visual_state() -> Dictionary:
	return {"role": role_id, "foe_visual": foe_visual,
			"mesh_rows": _mesh_rows.size(),
			"light_rows": _light_rows.size(),
			"foe_materials": _foe_materials.size()}


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
	_apply_stance_bias()
	frames_applied += 1


func _draw() -> void:
	if sv == null:
		return
	var t := sv.get_texture()
	if t == null:
		return
	# I 路线：只有启用 foe 视觉时改绘制尺寸；玩家侧乘 1.0 精确不变。
	var sx := FOE_DRAW_SCALE_X if foe_visual else 1.0
	var sy := FOE_DRAW_SCALE_Y if foe_visual else 1.0
	var w := float(SV_W) * DRAW_SCALE * sx
	var h := float(SV_H) * DRAW_SCALE * sy
	# 水平镜像用负宽度 Rect2（不能碰 draw_set_transform：它会覆盖节点
	# 自身 transform，把 arena 设的 position 吃掉，层就画到 (0,0) 了）。
	var x0 := DRAW_OFFSET_X - w * 0.5
	if view_flip:
		draw_texture_rect(t, Rect2(x0 + w, -h + DRAW_OFFSET_Y, -w, h), false)
	else:
		draw_texture_rect(t, Rect2(x0, -h + DRAW_OFFSET_Y, w, h), false)
	tex_drawn = true


func _process(_d: float) -> void:
	if ready_ok:
		queue_redraw()
