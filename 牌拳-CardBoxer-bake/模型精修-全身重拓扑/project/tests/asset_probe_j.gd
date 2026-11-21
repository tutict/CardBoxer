extends SceneTree
## J 路线 P0c：引擎内读回两侧 3D 层的真实资产，定位「同源」是资产还是渲染。
##
## 同进程三帧：
##   base      = 无 3D 层
##   foe-only  = 只挂 foe 层
##   both      = 再挂 player 层
## 每帧额外把各层 SubViewport 的 ViewportTexture 单独存成 PNG，
## 这样「2D 合成后看到什么」与「SubViewport 里到底渲了什么」能分开判。
##
## 跑法（必须带窗口）：
##   J_ASSET_DIR=<abs> godot --path . --resolution 1280x720 \
##     --quit-after 900 --script res://tests/asset_probe_j.gd

const ArenaScene = preload("res://scenes/main.tscn")


class Driver:
	extends Node

	const LayerScript = preload("res://scripts/fighter_3d_layer.gd")
	const MOTION_P := "res://data/motion_input.json"
	const MOTION_F := "res://data/motion_input_foe.json"
	const WARM := 20

	var arena: Node2D
	var out_dir := ""
	var motion_p: Dictionary = {}
	var motion_f: Dictionary = {}
	var initialized := false
	var busy := false
	var stage := 0
	var wait := 0
	var rows: Array = []

	func _snap(name: String) -> void:
		await RenderingServer.frame_post_draw
		var img := get_viewport().get_texture().get_image()
		var path := out_dir + "/j-" + name + ".png"
		var err := img.save_png(path)
		rows.append({"name": name, "path": path,
			"w": img.get_width(), "h": img.get_height(),
			"save_error": int(err)})

	func _mesh_info(layer) -> Dictionary:
		var out := {"glb_path": String(layer.glb_path),
			"role": String(layer.role_id),
			"sv_instance_id": 0, "tex_instance_id": 0,
			"sv_size": [0, 0], "meshes": []}
		if layer.sv == null:
			return out
		# Godot 4.5 的 SubViewport / ViewportTexture 都不是 CanvasItem，
		# 没有 get_rid()；用 Object.get_instance_id() 判「是否同一个对象」。
		out["sv_instance_id"] = int(layer.sv.get_instance_id())
		out["sv_size"] = [layer.sv.size.x, layer.sv.size.y]
		# layer 是无类型参数，:= 推不出 get_texture() 的返回类型；
		# 用无类型 var，后面判空即可（GDScript Parse Error 实测踩到）。
		var t = layer.sv.get_texture()
		if t != null:
			out["tex_instance_id"] = int(t.get_instance_id())
			var im = t.get_image()
			if im != null:
				var p := out_dir + "/j-sv-" + String(layer.role_id) + ".png"
				out["sv_png"] = p
				out["sv_png_error"] = int(im.save_png(p))
		_collect(layer.sv, out["meshes"], String(layer.role_id))
		return out

	func _collect(n: Node, rows: Array, role: String) -> void:
		if n is MeshInstance3D:
			var mi := n as MeshInstance3D
			var row := {"name": mi.name, "surfaces": 0,
				"verts": 0, "albedo": "", "material": ""}
			if mi.mesh != null:
				row["surfaces"] = mi.mesh.get_surface_count()
				var arr = mi.mesh.surface_get_arrays(0)
				if arr.size() > Mesh.ARRAY_VERTEX and arr[Mesh.ARRAY_VERTEX] != null:
					row["verts"] = arr[Mesh.ARRAY_VERTEX].size()
				var m = mi.mesh.surface_get_material(0)
				if m != null:
					row["material"] = m.get_class()
					if m is StandardMaterial3D:
						var sm := m as StandardMaterial3D
						if sm.albedo_texture != null:
							row["albedo"] = sm.albedo_texture.resource_path
							# 直接读回引擎里这张贴图的像素，排除「磁盘 PNG 是暗的、
							# 但 .godot 导入缓存串成玩家亮图」这一假设。
							var ai = sm.albedo_texture.get_image()
							if ai != null:
								var p := out_dir + "/j-albedo-" + role + ".png"
								row["albedo_png"] = p
								row["albedo_png_error"] = int(ai.save_png(p))
								var acc := Vector3.ZERO
								var steps := 16
								for gy in range(steps):
									for gx in range(steps):
										var px := ai.get_pixel(
											int(float(gx) * ai.get_width() / steps),
											int(float(gy) * ai.get_height() / steps))
										acc += Vector3(px.r, px.g, px.b)
								acc /= float(steps * steps)
								row["albedo_sample_mean"] = [acc.x, acc.y, acc.z]
						row["albedo_color"] = [
							sm.albedo_color.r, sm.albedo_color.g,
							sm.albedo_color.b]
			rows.append(row)
		for c in n.get_children():
			_collect(c, rows, role)

	func _attach_foe() -> void:
		var lf := LayerScript.new()
		lf.configure("foe", LayerScript.FOE_GLB_PATH,
				LayerScript.DEFAULT_FOE_YAW, false)
		arena.world.add_child(lf)
		if lf.setup(motion_f):
			arena.layer_3d_foe = lf
			arena.motion_3d_foe = motion_f
			lf.position = arena.enemy.position + arena.enemy.visual_shift
			arena.enemy.draw_3d_override = true

	func _attach_player() -> void:
		var lp := LayerScript.new()
		arena.world.add_child(lp)
		if lp.setup(motion_p):
			arena.layer_3d = lp
			arena.motion_3d = motion_p
			lp.position = arena.player.position + arena.player.visual_shift
			arena.player.draw_3d_override = true

	func _process(_d: float) -> void:
		if busy:
			return
		busy = true
		if not initialized:
			initialized = true
			arena.paused = true
			for c in arena.get_children():
				if c.name != "World":
					c.visible = false
			var pp: Variant = JSON.parse_string(
					FileAccess.get_file_as_string(MOTION_P))
			if pp is Dictionary:
				motion_p = pp
			var ff: Variant = JSON.parse_string(
					FileAccess.get_file_as_string(MOTION_F))
			if ff is Dictionary:
				motion_f = ff
		wait += 1
		if wait < WARM:
			busy = false
			return
		wait = 0
		if stage == 0:
			await _snap("base")
			_attach_foe()
		elif stage == 1:
			await _snap("foe-only")
			_attach_player()
		elif stage == 2:
			await _snap("both")
			var payload := {
				"shots": rows,
				"foe": _mesh_info(arena.layer_3d_foe)
						if arena.layer_3d_foe != null else {},
				"player": _mesh_info(arena.layer_3d)
						if arena.layer_3d != null else {},
			}
			var f := FileAccess.open(out_dir + "/j_asset_result.json",
					FileAccess.WRITE)
			if f != null:
				f.store_string(JSON.stringify(payload, "\t"))
				f.close()
			print("JASSET_JSON " + JSON.stringify(payload))
			get_tree().quit(0)
			return
		stage += 1
		busy = false


func _init() -> void:
	var out_dir := OS.get_environment("J_ASSET_DIR")
	if out_dir == "":
		print("JASSET_JSON " + JSON.stringify({"error": "J_ASSET_DIR missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var inst: Node2D = (ArenaScene as PackedScene).instantiate()
	root.add_child(inst)
	var d := Driver.new()
	d.arena = inst
	d.out_dir = out_dir
	root.add_child(d)
	print("JASSET_START out=%s" % out_dir)
