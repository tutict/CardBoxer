extends SceneTree
## Godot 4.5 导入探针：把 GLB 作为 PackedScene load 回来，逐节点读回结构。
##
##   godot --headless --path <probe_project> --script res://probes/inspect_import.gd
##
## 只输出一行 PROBE_JSON 供外部 Python 落盘；不在工程里写任何文件。
## 这是「导入可行性量测」，不是把资产接进可运行游戏工程。

const TARGETS := [
	"res://assets/foe-full.glb",
	"res://assets/foe-stance.glb",
	"res://assets/foe-proxy-rig.glb",
]


func _tex_info(tex: Texture2D) -> Dictionary:
	if tex == null:
		return {"present": false}
	return {"present": true, "w": tex.get_width(), "h": tex.get_height()}


func _material_info(mat: Material) -> Dictionary:
	if mat == null:
		return {"present": false}
	var out := {"present": true, "class": mat.get_class()}
	if mat is BaseMaterial3D:
		var bm := mat as BaseMaterial3D
		out["albedo"] = _tex_info(bm.albedo_texture)
		out["normal"] = _tex_info(bm.normal_texture)
		out["metallic"] = _tex_info(bm.metallic_texture)
		out["roughness"] = _tex_info(bm.roughness_texture)
		out["ao"] = _tex_info(bm.ao_texture)
	return out


func _vec3(v: Vector3) -> Array:
	return [round(v.x * 10000.0) / 10000.0,
			round(v.y * 10000.0) / 10000.0,
			round(v.z * 10000.0) / 10000.0]


func _walk(n: Node, row: Dictionary) -> void:
	var t := n.get_class()
	row["types"][t] = int(row["types"].get(t, 0)) + 1
	row["node_count"] = int(row["node_count"]) + 1

	if n is MeshInstance3D:
		var mi := n as MeshInstance3D
		var mesh := mi.mesh
		var mrow := {"name": String(n.name), "has_mesh": mesh != null}
		if mesh != null:
			var verts := 0
			for s in range(mesh.get_surface_count()):
				var arr := mesh.surface_get_arrays(s)
				if arr.size() > Mesh.ARRAY_VERTEX and arr[Mesh.ARRAY_VERTEX] != null:
					verts += (arr[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
			var box := mesh.get_aabb()
			mrow["surfaces"] = mesh.get_surface_count()
			mrow["verts"] = verts
			mrow["aabb_pos"] = _vec3(box.position)
			mrow["aabb_size"] = _vec3(box.size)
			mrow["material"] = _material_info(mesh.surface_get_material(0))
			mrow["skeleton_path"] = String(mi.get_skeleton_path())
		row["mesh_instances"].append(mrow)

	if n is Skeleton3D:
		var sk := n as Skeleton3D
		var names := []
		for i in range(min(sk.get_bone_count(), 16)):
			names.append(String(sk.get_bone_name(i)))
		row["skeletons"].append({
			"name": String(n.name), "bones": sk.get_bone_count(),
			"bone_names_head": names})

	if n is AnimationPlayer:
		var ap := n as AnimationPlayer
		row["animation_players"].append({
			"name": String(n.name),
			"animations": Array(ap.get_animation_list())})

	for c in n.get_children():
		_walk(c, row)


func _probe(path: String) -> Dictionary:
	var row := {
		"path": path, "load_ok": false, "resource_class": "",
		"types": {}, "node_count": 0, "mesh_instances": [],
		"skeletons": [], "animation_players": [],
	}
	var res := load(path)
	if res == null:
		row["error"] = "load returned null"
		return row
	row["load_ok"] = true
	row["resource_class"] = res.get_class()
	if res is PackedScene:
		var inst := (res as PackedScene).instantiate()
		root.add_child(inst)
		_walk(inst, row)
		inst.queue_free()
	else:
		row["error"] = "not a PackedScene"
	return row


func _init() -> void:
	var out := {"engine": Engine.get_version_info(), "targets": []}
	for p in TARGETS:
		out["targets"].append(_probe(p))
	print("PROBE_JSON " + JSON.stringify(out))
	quit(0)
