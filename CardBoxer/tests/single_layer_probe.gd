extends SceneTree
## B 路线 P0：单进程只挂一个 3D 层，取该层 SubViewport 原图。
##
## 同一份代码被 runner 调用两次（foe / player），靠环境变量区分，
## 从根上排除「多 SubViewport 同帧 get_image() 标签错位」这个干扰。
## 不改 GLB / 贴图 / 任何玩法源码。
##
## 跑法：
##   SINGLE_OUT=<abs> SINGLE_ROLE=foe|player SINGLE_GLB=<res://...> \
##   SINGLE_YAW=<deg> godot --path . --resolution 1280x720 \
##     --quit-after 900 --script res://tests/single_layer_probe.gd

const LayerScript = preload("res://scripts/fighter_3d_layer.gd")


class Driver:
	extends Node

	const WARM := 30
	var out_dir := ""
	var role := ""
	var glb := ""
	var yaw := 0.0
	var motion_file := ""
	var lf: Node2D = null
	var wait := 0
	var busy := false
	var done := false
	var initialized := false


	func _mesh_rows(n: Node, acc: Array) -> void:
		if n is MeshInstance3D:
			var mi := n as MeshInstance3D
			var rec := {"name": String(mi.name), "surfaces": 0,
				"verts": 0, "albedo": ""}
			if mi.mesh != null:
				rec["surfaces"] = mi.mesh.get_surface_count()
				var arr = mi.mesh.surface_get_arrays(0)
				if arr.size() > Mesh.ARRAY_VERTEX \
						and arr[Mesh.ARRAY_VERTEX] != null:
					rec["verts"] = arr[Mesh.ARRAY_VERTEX].size()
				var m = mi.mesh.surface_get_material(0)
				if m is StandardMaterial3D:
					var sm := m as StandardMaterial3D
					if sm.albedo_texture != null:
						rec["albedo"] = String(
							sm.albedo_texture.resource_path)
					rec["metallic"] = sm.metallic
			acc.append(rec)
		for c in n.get_children():
			_mesh_rows(c, acc)


	func _init_layer() -> bool:
		var pp: Variant = JSON.parse_string(
			FileAccess.get_file_as_string(motion_file))
		var motion: Dictionary = {}
		if pp is Dictionary:
			motion = pp
		lf = LayerScript.new()
		lf.configure(role, glb, yaw, false)
		# 必须在首帧（已在 tree 中）建层：_init() 阶段 add_child 后
		# Camera3D.look_at() 会报 "Node not inside tree"，渲出全透明图。
		get_tree().root.add_child(lf)
		return lf.setup(motion)


	func _process(_d: float) -> void:
		if busy or done:
			return
		busy = true
		if not initialized:
			initialized = true
			if not _init_layer():
				print("SINGLE_JSON " + JSON.stringify(
					{"error": "layer setup failed"}))
				get_tree().quit(1)
				return
		wait += 1
		if wait < WARM:
			busy = false
			return
		done = true
		await RenderingServer.frame_post_draw
		var meshes: Array = []
		_mesh_rows(lf.sv, meshes)
		var out := {"role": role, "glb": String(lf.glb_path),
			"yaw": float(lf.view_yaw_deg), "meshes": meshes,
			"sv_png": "", "sv_error": -1}
		var t = lf.sv.get_texture()
		if t != null:
			var im = t.get_image()
			if im != null:
				var p := out_dir + "/single-" + role + ".png"
				out["sv_png"] = p
				out["sv_error"] = int(im.save_png(p))
				out["sv_size"] = [im.get_width(), im.get_height()]
		print("SINGLE_JSON " + JSON.stringify(out))
		get_tree().quit(0)


func _init() -> void:
	var out_dir := OS.get_environment("SINGLE_OUT")
	var role := OS.get_environment("SINGLE_ROLE")
	var glb := OS.get_environment("SINGLE_GLB")
	var yaw := float(OS.get_environment("SINGLE_YAW"))
	if out_dir == "" or role == "" or glb == "":
		print("SINGLE_JSON " + JSON.stringify(
			{"error": "SINGLE_* env missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var motion_file := ("res://data/motion_input_foe.json" if role == "foe"
		else "res://data/motion_input.json")
	var d := Driver.new()
	d.out_dir = out_dir
	d.role = role
	d.glb = glb
	d.yaw = yaw
	d.motion_file = motion_file
	root.add_child(d)
