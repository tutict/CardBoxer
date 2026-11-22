extends SceneTree
## Read-only metadata from the cached Godot GLB PackedScenes, independent of drivers.

func _v(v: Vector3) -> Array:
	return [v.x, v.y, v.z]

func _q(q: Quaternion) -> Array:
	return [q.x, q.y, q.z, q.w]

func _t(t: Transform3D) -> Dictionary:
	return {"origin": _v(t.origin), "basis_columns": [_v(t.basis.x), _v(t.basis.y), _v(t.basis.z)],
		"scale": _v(t.basis.get_scale()), "quaternion": _q(t.basis.get_rotation_quaternion()),
		"determinant": t.basis.determinant()}

func _skeleton(n: Node) -> Skeleton3D:
	if n is Skeleton3D:
		return n
	for c in n.get_children():
		var s := _skeleton(c)
		if s != null:
			return s
	return null

func _nodes(n: Node, rows: Array) -> void:
	if n is Node3D:
		rows.append({"path": String(n.get_path()), "type": n.get_class(),
			"local_transform": _t(n.transform), "global_transform": _t(n.global_transform)})
	for c in n.get_children():
		_nodes(c, rows)

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var out := OS.get_environment("NATIVE_RIG_OUT")
	if out.is_empty():
		out = ProjectSettings.globalize_path("res://../reports/rig-rest.json")
	var payload := {"source": "Godot cached GLB PackedScene / Skeleton3D", "godot": Engine.get_version_info(),
		"coordinate_system": "godot_y_up_z_forward", "basis_layout": "columns x,y,z", "roles": {}}
	for role in ["player", "foe"]:
		var path: String = "res://assets/3d/" + String(role) + "-rigged.glb"
		var packed := load(path) as PackedScene
		if packed == null:
			push_error("Cannot load cached GLB: " + path)
			quit(1)
			return
		var model := packed.instantiate() as Node3D
		root.add_child(model)
		var skel := _skeleton(model)
		if skel == null:
			push_error("Skeleton missing: " + path)
			quit(1)
			return
		var nodes: Array = []
		_nodes(model, nodes)
		var bones: Array = []
		for i in range(skel.get_bone_count()):
			var p := skel.get_bone_parent(i)
			var children: Array = []
			var endpoints: Array = []
			for child in skel.get_bone_children(i):
				children.append(skel.get_bone_name(child))
				endpoints.append({"source": "child rest origin", "child": skel.get_bone_name(child),
					"skeleton_position": _v(skel.get_bone_global_rest(child).origin),
					"world_position": _v(skel.global_transform * skel.get_bone_global_rest(child).origin)})
			var gr := skel.get_bone_global_rest(i)
			bones.append({"index": i, "name": skel.get_bone_name(i), "parent_index": p,
				"parent": skel.get_bone_name(p) if p >= 0 else "", "children": children,
				"local_rest": _t(skel.get_bone_rest(i)), "global_rest": _t(gr),
				"initial_pose": _t(skel.get_bone_pose(i)), "world_rest": _t(skel.global_transform * gr),
				"endpoints": endpoints,
				"leaf_endpoint_note": "Godot Skeleton3D has no imported bone-tail metadata; only joint origins are exact" if endpoints.is_empty() else ""})
		payload.roles[role] = {"asset": path, "model_transform": _t(model.transform),
			"model_global_transform": _t(model.global_transform), "skeleton_path": String(skel.get_path()),
			"skeleton_transform": _t(skel.transform), "skeleton_global_transform": _t(skel.global_transform),
			"nodes": nodes, "bones": bones}
		model.free()
	DirAccess.make_dir_recursive_absolute(out.get_base_dir())
	var file := FileAccess.open(out, FileAccess.WRITE)
	if file == null:
		push_error("Cannot write " + out)
		quit(1)
		return
	file.store_string(JSON.stringify(payload, "\t"))
	file.close()
	print("NATIVE_RIG_REST " + out)
	quit(0)
