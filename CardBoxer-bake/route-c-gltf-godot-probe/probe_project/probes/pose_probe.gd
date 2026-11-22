extends SceneTree
## 引擎内手动驱动 Skeleton3D，确认 glTF 带进来的骨架/skin 关系是否真的可用。
##
## 注意 CPU 侧 mesh 顶点不会因 GPU skinning 改变；本探针只证明
## 「骨骼 pose 可改 + 哪个 MeshInstance3D 绑到骨架」，不冒充视觉变形证据。

const FULL := "res://assets/foe-full.glb"


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
		out.append({
			"name": String(n.name),
			"skeleton_path": String(mi.get_skeleton_path()),
			"skin_present": mi.skin != null,
		})
	for c in n.get_children():
		_collect_meshes(c, out)


func _v(v: Vector3) -> Array:
	return [round(v.x * 100000.0) / 100000.0,
			round(v.y * 100000.0) / 100000.0,
			round(v.z * 100000.0) / 100000.0]


func _init() -> void:
	var out := {"path": FULL, "load_ok": false}
	var res := load(FULL)
	if res == null:
		print("POSE_JSON " + JSON.stringify(out))
		quit(1)
	var inst := (res as PackedScene).instantiate()
	root.add_child(inst)
	out["load_ok"] = true
	var sk := _find_skel(inst)
	out["skeleton_found"] = sk != null
	if sk == null:
		print("POSE_JSON " + JSON.stringify(out))
		quit(1)
	out["bone_count"] = sk.get_bone_count()
	var idx := sk.find_bone("upperarm_f")
	out["target_bone_index"] = idx
	if idx < 0:
		print("POSE_JSON " + JSON.stringify(out))
		quit(1)
	# 判据用 get_bone_pose_rotation（本地 pose，写入即读回）；
	# global pose 在 headless 的 _init() 单帧里脏标记未刷新，只作观察值，
	# 不拿来当「能不能驱动」的证据。
	var q_before := sk.get_bone_pose_rotation(idx)
	var before := sk.get_bone_global_pose(idx)
	sk.set_bone_pose_rotation(idx, Quaternion(Vector3(0, 0, 1), deg_to_rad(35.0)))
	var q_after := sk.get_bone_pose_rotation(idx)
	var after := sk.get_bone_global_pose(idx)
	out["pose_local_changed"] = not q_before.is_equal_approx(q_after)
	out["before_origin"] = _v(before.origin)
	out["after_origin"] = _v(after.origin)
	out["global_pose_changed_in_headless"] = not before.is_equal_approx(after)
	var meshes := []
	_collect_meshes(inst, meshes)
	out["meshes"] = meshes
	var bound := 0
	var unbound := 0
	for m in meshes:
		if m["skeleton_path"] != "":
			bound += 1
		else:
			unbound += 1
	out["bound_mesh_count"] = bound
	out["unbound_mesh_count"] = unbound
	print("POSE_JSON " + JSON.stringify(out))
	quit(0)
