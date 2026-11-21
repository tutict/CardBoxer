extends SceneTree
## I 路线 P0：读回两份 GLB 在 Godot 里的真实材质参数。
## 目的：确认能否用 StandardMaterial3D.duplicate() 做运行时 tint，
## 而不是靠猜 GLB 导入后是什么材质类。
##
## 跑法：godot --headless --path . --script res://tests/material_probe.gd

const PLAYER_GLB := "res://assets/3d/player-rigged.glb"
const FOE_GLB := "res://assets/3d/foe-rigged.glb"


func _collect(n: Node, out: Array) -> void:
	if n is MeshInstance3D:
		out.append(n)
	for c in n.get_children():
		_collect(c, out)


func _info(res_path: String) -> Dictionary:
	var res := load(res_path)
	if res == null or not (res is PackedScene):
		return {"path": res_path, "error": "load failed"}
	var inst: Node = (res as PackedScene).instantiate()
	var meshes: Array = []
	_collect(inst, meshes)
	var rows: Array = []
	for m in meshes:
		var mi := m as MeshInstance3D
		var mesh := mi.mesh
		if mesh == null:
			rows.append({"mesh": mi.name, "error": "null mesh"})
			continue
		for i in range(mesh.get_surface_count()):
			var mat: Material = mesh.surface_get_material(i)
			var d := {
				"mesh": String(mi.name), "surface": i,
				"material_class": mat.get_class() if mat != null else "null",
			}
			if mat is StandardMaterial3D:
				var sm := mat as StandardMaterial3D
				d["albedo_color"] = [sm.albedo_color.r, sm.albedo_color.g,
					sm.albedo_color.b, sm.albedo_color.a]
				d["albedo_texture"] = (sm.albedo_texture.resource_path
					if sm.albedo_texture != null else "")
				d["metallic"] = sm.metallic
				d["roughness"] = sm.roughness
				d["metallic_texture"] = (sm.metallic_texture.resource_path
					if sm.metallic_texture != null else "")
				d["normal_texture"] = (sm.normal_texture.resource_path
					if sm.normal_texture != null else "")
			rows.append(d)
	return {"path": res_path, "surfaces": rows}


func _init() -> void:
	var out := {"player": _info(PLAYER_GLB), "foe": _info(FOE_GLB)}
	print("IMAT_JSON " + JSON.stringify(out))
	quit(0)
