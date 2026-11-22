extends SceneTree
## F 路线阶段 4 前置：headless 数值探针，量出 Godot 4.5 导入 GLB 后
## Skeleton3D 的 rest 基底、骨骼层级、mesh/skin 绑定关系。
##
## 目的：Blender 的 pb.matrix = D[name] @ bone.matrix_local 是 armature
## space 的层级增量；glTF export_yup=True 之后，Godot 里骨骼 rest 的轴
## 朝向必须由实测决定，不能手推。这里把 origin / basis / parent /
## global_transform 全部读回，交给 crosscheck_godot_rest.py 做独立对账。
##
## 注意：headless 单帧里 get_bone_global_pose 的脏标记可能没刷新，本探针
## 只读 rest（静态数据）与 pose 的「写入即读回」，不拿 global pose 当证据。

const GLB_PATH := "res://assets/player-rigged.glb"


func _v3(v: Vector3) -> Array:
	return [round(v.x * 1000000.0) / 1000000.0,
			round(v.y * 1000000.0) / 1000000.0,
			round(v.z * 1000000.0) / 1000000.0]


func _q4(q: Quaternion) -> Array:
	return [round(q.w * 1000000.0) / 1000000.0,
			round(q.x * 1000000.0) / 1000000.0,
			round(q.y * 1000000.0) / 1000000.0,
			round(q.z * 1000000.0) / 1000000.0]


func _t3(t: Transform3D) -> Dictionary:
	return {
		"origin": _v3(t.origin),
		"quat": _q4(t.basis.get_rotation_quaternion()),
		"scale": _v3(t.basis.get_scale()),
		"basis_rows": [_v3(t.basis.x), _v3(t.basis.y), _v3(t.basis.z)],
	}


func _find_skel(n: Node) -> Skeleton3D:
	if n is Skeleton3D:
		return n as Skeleton3D
	for c in n.get_children():
		var r := _find_skel(c)
		if r != null:
			return r
	return null


func _collect_meshes(n: Node, out: Array) -> void:
	if n is MeshInstance3D:
		var mi := n as MeshInstance3D
		var aabb := AABB()
		if mi.mesh != null:
			aabb = mi.mesh.get_aabb()
		out.append({
			"name": String(n.name),
			"skeleton_path": String(mi.get_skeleton_path()),
			"skin_present": mi.skin != null,
			"verts": mi.mesh.get_faces().size() if mi.mesh != null else 0,
			"aabb_pos": _v3(aabb.position),
			"aabb_size": _v3(aabb.size),
		})
	for c in n.get_children():
		_collect_meshes(c, out)


func _init() -> void:
	var out := {"path": GLB_PATH, "load_ok": false}
	var res := load(GLB_PATH)
	if res == null or not (res is PackedScene):
		out["error"] = "GLB load failed"
		print("RIG_JSON " + JSON.stringify(out))
		quit(1)
		return
	var inst := (res as PackedScene).instantiate()
	root.add_child(inst)
	out["load_ok"] = true
	var sk := _find_skel(inst)
	out["skeleton_found"] = sk != null
	if sk == null:
		print("RIG_JSON " + JSON.stringify(out))
		quit(1)
		return
	out["skeleton_name"] = String(sk.name)
	out["skeleton_global_transform"] = _t3(sk.global_transform)
	out["bone_count"] = sk.get_bone_count()
	var bones := []
	for i in range(sk.get_bone_count()):
		var gr := sk.get_bone_global_rest(i)
		var lr := sk.get_bone_rest(i)
		var has_force := sk.has_method("force_update_all_bone_transforms")
		bones.append({
			"index": i,
			"name": String(sk.get_bone_name(i)),
			"parent": sk.get_bone_parent(i),
			"global_rest": _t3(gr),
			"local_rest": _t3(lr),
			"pose_rotation": _q4(sk.get_bone_pose_rotation(i)),
			"pose_position": _v3(sk.get_bone_pose_position(i)),
			"pose_scale": _v3(sk.get_bone_pose_scale(i)),
		})
		if i == 0:
			out["has_force_update"] = has_force
	out["bones"] = bones

	# pose 可写性：写入即读回（不依赖 global pose 刷新）。
	var idx := sk.find_bone("upperarm_f")
	out["upperarm_f_index"] = idx
	if idx >= 0:
		var probe_q := Quaternion(Vector3(0.0, 0.0, 1.0), deg_to_rad(30.0))
		sk.set_bone_pose_rotation(idx, probe_q)
		out["pose_writable"] = sk.get_bone_pose_rotation(idx).is_equal_approx(probe_q)
		sk.set_bone_pose_rotation(idx, Quaternion.IDENTITY)

	var meshes := []
	_collect_meshes(inst, meshes)
	out["meshes"] = meshes
	print("RIG_JSON " + JSON.stringify(out))
	quit(0)
