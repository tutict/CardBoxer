class_name RigDriver
extends RefCounted
## F 路线核心：Godot 4.5 运行时 14 骨驱动层。
##
## 输入只有 res://data/motion_input.json —— 原始 2D 关节表 + retarget
## 参数 + A-pose 关节点（米）。**不读任何烘死的 pose / quat / 动画**：
## make_points / angle / wrap_pi / retarget_delta / root 位移全部在
## GDScript 里现算，与 crosscheck_motion_input.py 同公式。
##
## 坐标口径由 data/godot_rig_probe.json 实测确定（Blender export_yup）：
##   Godot (X, Y, Z) = Blender (x, z, -y)。
##   apose_points[u] = (hx, hz)_Blender -> hv = (hx, hz, 0)_Godot。
##   mRotY(theta)_Blender == RotZ(-theta)_Godot。
##
## Blender: pb.matrix = D[name] @ bone.matrix_local,
##          D[name] = D[parent] @ local, local = T(hv) @ R @ T(-hv)。
##
## Godot 4 实测（data/godot_rig_probe.json）：bone_pose 的初值 == local_rest，
## 即 pose[i] 是「相对父骨的绝对变换」，不是相对 rest 的增量；
##   global_pose[i] = global_pose[parent] @ pose[i]。
## 令目标 global_pose[i] = D[i] @ GR[i]，且 D[i] = D[parent] @ local[i]：
##   pose[i] = GR[parent]^-1 @ local[i] @ GR[i]      （非根骨）
##   pose[root] = D[root] @ GR[root]                  （根骨含 root 平移）
## 注意基底是 **父骨** 的 global_rest，不是本骨的；第一版用 GR[i]^-1
## 会把 pose 写成相对本骨 rest 的增量，实测引擎骨架完全不动。
##
## 第 14 根 neutral_bone 是 glTF 导入器生成的独立根骨，不参与驱动，
## 保持导入时的 pose（其初值不是 identity，是一个 -90° X 旋转）。

var skel: Skeleton3D
var motion: Dictionary = {}
var bone_names: Array = []
var chain: Array = []
var mapping: Dictionary = {}
var stance: Dictionary = {}
var stance_points: Dictionary = {}
var apose: Dictionary = {}
var px_to_m: float = 0.01
var global_rest: Dictionary = {}
var bone_idx: Dictionary = {}

var frame_count_applied: int = 0
var last_delta_deg: Dictionary = {}
var last_root_m: Array = [0.0, 0.0]


func _v2(a: Array) -> Vector2:
	return Vector2(float(a[0]), float(a[1]))


func setup(p_skel: Skeleton3D, p_motion: Dictionary) -> bool:
	skel = p_skel
	motion = p_motion
	if skel == null:
		return false
	bone_names = motion.get("bones", [])
	chain = motion.get("chain", [])
	mapping = motion.get("mapping", {})
	apose = motion.get("apose_points", {})
	px_to_m = float(motion.get("px_to_m", 0.01))
	for k in motion["stance"].keys():
		stance[k] = _v2(motion["stance"][k])
	stance_points = make_points(stance)
	for n in bone_names:
		var key := String(n)
		var i := skel.find_bone(key)
		if i < 0:
			return false
		bone_idx[key] = i
		global_rest[key] = skel.get_bone_global_rest(i)
	return bone_names.size() == 13 and chain.size() == 13


func _lerp2(a: Vector2, b: Vector2, t: float) -> Vector2:
	return a.lerp(b, t)


func angle(p: Vector2, q: Vector2) -> float:
	return atan2(q.y - p.y, q.x - p.x)


func wrap_pi(a: float) -> float:
	return fposmod(a + PI, TAU) - PI


func make_points(j: Dictionary) -> Dictionary:
	var hip: Vector2 = j["hip"]
	var sh: Vector2 = j["shoulder"]
	var hd: Vector2 = j["head"]
	return {
		"A": hip,
		"B": _lerp2(hip, sh, 0.26),
		"C": _lerp2(hip, sh, 0.60),
		"D": sh,
		"E": _lerp2(sh, hd, 0.58),
		"F": hd,
		"f_elbow": j["f_elbow"], "f_hand": j["f_hand"],
		"b_elbow": j["b_elbow"], "b_hand": j["b_hand"],
		"f_knee": j["f_knee"], "f_foot": j["f_foot"],
		"b_knee": j["b_knee"], "b_foot": j["b_foot"],
		"tf_head": Vector2(hip.x + 4.0, hip.y),
		"tb_head": Vector2(hip.x - 4.0, hip.y),
	}


## 与 F路线/crosscheck_motion_input.py:retarget 逐字同公式，返回「度」。
## 腿骨映射：hard 是 P2 上线的硬 clamp，atan 是 P3 的软限幅。
## mapping 没有 leg_mode 时回落 hard，旧动作表配新驱动行为不变。
func _leg(x: float, cap: float, mode: String) -> float:
	if mode == "atan":
		return cap * (2.0 / PI) * atan((PI / 2.0) * x / cap)
	return clampf(x, -cap, cap)


func retarget_delta(frame_j: Dictionary) -> Dictionary:
	var fp := make_points(frame_j)
	var raw := {}
	for e in chain:
		var n := String(e[0])
		var u := String(e[2])
		var v := String(e[3])
		raw[n] = rad_to_deg(wrap_pi(
			angle(fp[u], fp[v]) - angle(stance_points[u], stance_points[v])))
	var torso := rad_to_deg(wrap_pi(
		angle(fp["A"], fp["D"]) - angle(stance_points["A"], stance_points["D"])))
	var cap := float(mapping["torso_cap_deg"])
	var used := clampf(torso * float(mapping["torso_gain"]), -cap, cap)
	var mf: float = (frame_j["f_hand"] as Vector2).distance_to(
		stance["f_hand"] as Vector2)
	var mb: float = (frame_j["b_hand"] as Vector2).distance_to(
		stance["b_hand"] as Vector2)
	var tf := minf(1.0, mf / float(mapping["reach_norm_px"]))
	var tb := minf(1.0, mb / float(mapping["reach_norm_px"]))
	var tw: float = minf(1.0, minf(mf, mb) /
		float(mapping["wave_min_norm_px"])) * float(mapping["wave_arm_weight"])
	var af := maxf(tf, tw)
	var ab := maxf(tb, tw)
	var g: Dictionary = mapping["arm_gain_deg"]
	var leg_cap := float(mapping["leg_cap_deg"])
	var leg_mode: String = String(mapping.get("leg_mode", "hard"))
	return {
		"hips": 0.0,
		"spine": used,
		"chest": 0.0,
		"neck": 0.0,
		"head": -used * float(mapping["head_compensation"]),
		"upperarm_f": -float(g["f_upper"]) * af,
		"forearm_f": -float(g["f_fore"]) * af,
		"upperarm_b": float(g["b_upper"]) * ab,
		"forearm_b": float(g["b_fore"]) * ab,
		"thigh_f": _leg(float(raw["thigh_f"]), leg_cap, leg_mode),
		"shin_f": _leg(float(raw["shin_f"]), leg_cap, leg_mode),
		"thigh_b": _leg(float(raw["thigh_b"]), leg_cap, leg_mode),
		"shin_b": _leg(float(raw["shin_b"]), leg_cap, leg_mode),
	}


func _joints_of(card: String, frame: int) -> Dictionary:
	if card == "stance" or card == "":
		return stance
	var raw: Dictionary = motion["cards"][card]["track"][frame]
	var out := {}
	for k in raw.keys():
		out[k] = _v2(raw[k])
	return out


func _v3(v: Vector3) -> Array:
	return [round(v.x * 1000000.0) / 1000000.0,
			round(v.y * 1000000.0) / 1000000.0,
			round(v.z * 1000000.0) / 1000000.0]


## 驱动一帧；返回可供数值对账的 13 骨 global pose 与 delta。
func apply_frame(card: String, frame: int) -> Dictionary:
	var frame_j := _joints_of(card, frame)
	var delta_deg := retarget_delta(frame_j)
	var dx: float = (frame_j["hip"].x - stance["hip"].x) * px_to_m
	var dz: float = -(frame_j["hip"].y - stance["hip"].y) * px_to_m
	last_delta_deg = delta_deg
	last_root_m = [dx, dz]

	var cum: Dictionary = {}
	var calc_global: Dictionary = {}
	var delta_rows: Dictionary = {}
	for e in chain:
		var n := String(e[0])
		var parent: Variant = e[1]
		var u := String(e[2])
		var hv := Vector3(float(apose[u][0]), float(apose[u][1]), 0.0)
		var theta := -deg_to_rad(float(delta_deg[n]))
		var rot := Quaternion(Vector3(0.0, 0.0, 1.0), theta)
		# T(hv) @ R @ T(-hv) —— 绕 A-pose 关节点的全局增量旋转。
		var local := (Transform3D(Basis.IDENTITY, hv)
			* Transform3D(Basis(rot), Vector3.ZERO)
			* Transform3D(Basis.IDENTITY, -hv))
		var c: Transform3D
		if parent == null:
			c = Transform3D(Basis.IDENTITY, Vector3(dx, dz, 0.0)) * local
		else:
			c = (cum[String(parent)] as Transform3D) * local
		cum[n] = c
		var gr: Transform3D = global_rest[n]
		calc_global[n] = c * gr

		# pose = GR[parent]^-1 @ local @ GR[i]；根骨用 D[root] @ GR[root]。
		var gr_parent: Transform3D
		if parent == null:
			gr_parent = Transform3D.IDENTITY
		else:
			gr_parent = global_rest[String(parent)]
		var pose_mat := gr_parent.affine_inverse() * local * gr
		if parent == null:
			pose_mat = c * gr
		var i: int = bone_idx[n]
		skel.set_bone_pose_position(i, pose_mat.origin)
		skel.set_bone_pose_rotation(i, pose_mat.basis.get_rotation_quaternion())
		skel.set_bone_pose_scale(i, pose_mat.basis.get_scale())
		delta_rows[n] = round(float(delta_deg[n]) * 100000.0) / 100000.0

	frame_count_applied += 1
	var out_global := {}
	for n in bone_names:
		out_global[String(n)] = _v3((calc_global[n] as Transform3D).origin)
	return {
		"card": card, "frame": frame,
		"root_m": [round(dx * 1000000.0) / 1000000.0,
				   round(dz * 1000000.0) / 1000000.0],
		"delta_deg": delta_rows,
		"calc_global_origin": out_global,
		"bones_driven": chain.size(),
	}
