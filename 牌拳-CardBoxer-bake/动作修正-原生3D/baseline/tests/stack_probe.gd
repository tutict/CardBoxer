extends SceneTree
## B 路线 P0 决定性探针：foe 层 SubViewport 里的「白布青云纹」来自哪一层。
##
## 同进程 4 个状态，每个状态直接取 SubViewport 的 ViewportTexture 存 PNG：
##   s-0-orig      原样（四盏灯 + metallic=1.0 + foe 暗灰 baseColor）
##   s-1-lights0   四盏 DirectionalLight3D 能量全 0
##   s-2-nometal   灯恢复；材质 metallic=0 / roughness=1（贴图保留）
##   s-3-redalbedo 灯与 metallic 恢复；只把 albedo 换成纯红
##
## 判读：
##   s1 白布消失 ⇒ 灯光高光
##   s2 白布消失 ⇒ 金属镜面反射
##   s3 白布变红 ⇒ 形状来自几何，颜色来自 albedo
## 四帧都不动 GLB / 贴图文件 / 任何 .gd 玩法源码，只改运行时材质与灯。
##
## 跑法：
##   STACK_OUT=<abs> godot --path . --resolution 1280x720 \
##     --quit-after 900 --script res://tests/stack_probe.gd


class Driver:
	extends Node

	const LayerScript = preload("res://scripts/fighter_3d_layer.gd")
	const WARM := 25

	var lf: Node2D = null
	var rows: Array = []
	var stage := 0
	var wait := 0
	var busy := false
	var initialized := false
	var out_dir := ""
	var motion: Dictionary = {}
	var lights: Array = []
	var mesh_rows: Array = []
	var orig_mats: Array = []
	var light_energy0: Array = []


	func _collect(n: Node) -> void:
		if n is MeshInstance3D:
			var mi := n as MeshInstance3D
			if mi.mesh != null:
				for i in range(mi.mesh.get_surface_count()):
					var m = mi.mesh.surface_get_material(i)
					mesh_rows.append({"mi": mi, "surface": i, "mat": m})
					orig_mats.append(m)
		if n is DirectionalLight3D:
			lights.append(n)
		for c in n.get_children():
			_collect(c)


	func _snap(name: String) -> void:
		await RenderingServer.frame_post_draw
		if lf.sv == null:
			return
		var t = lf.sv.get_texture()
		if t == null:
			return
		var im = t.get_image()
		if im == null:
			return
		var p := out_dir + "/s-" + name + ".png"
		rows.append({"name": name, "path": p,
			"w": im.get_width(), "h": im.get_height(),
			"save_error": int(im.save_png(p))})


	func _material_slots() -> Array:
		var out: Array = []
		for row in mesh_rows:
			var m = row["mat"]
			var rec := {"mesh": String((row["mi"] as Node).name),
				"surface": int(row["surface"]),
				"class": m.get_class() if m != null else "NULL"}
			if m is StandardMaterial3D:
				var sm := m as StandardMaterial3D
				rec["albedo_color"] = [sm.albedo_color.r,
					sm.albedo_color.g, sm.albedo_color.b]
				rec["metallic"] = sm.metallic
				rec["roughness"] = sm.roughness
				var slots := {
					"albedo": sm.albedo_texture,
					"metallic": sm.metallic_texture,
					"roughness": sm.roughness_texture,
					"normal": sm.normal_texture,
					"emission": sm.emission_texture}
				for k in slots.keys():
					var tex = slots[k]
					rec[String(k) + "_texture"] = (
						String(tex.resource_path) if tex != null else "")
			out.append(rec)
		return out


	func _init_layer() -> bool:
		lf = LayerScript.new()
		lf.configure("foe", LayerScript.FOE_GLB_PATH,
			LayerScript.DEFAULT_FOE_YAW, false)
		get_tree().root.add_child(lf)
		if not lf.setup(motion):
			return false
		if lf.sv != null:
			_collect(lf.sv)
		for l in lights:
			light_energy0.append(
				float((l as DirectionalLight3D).light_energy))
		print("STACK_START meshes=%d lights=%d" % [mesh_rows.size(),
			lights.size()])
		return true


	func _restore_lights() -> void:
		for i in range(lights.size()):
			(lights[i] as DirectionalLight3D).light_energy = \
				float(light_energy0[i])


	## 复制原材质（保留全部 PBR 槽位），只改本次要隔离的那一项。
	## nometal = 关金属镜面（metallic/roughness 及其贴图全清）
	## red     = 只换 albedo，metallic 与灯保持原样
	func _variant(mode: String) -> StandardMaterial3D:
		var sm: StandardMaterial3D = null
		if orig_mats.size() > 0 and orig_mats[0] is StandardMaterial3D:
			sm = (orig_mats[0] as StandardMaterial3D).duplicate() \
				as StandardMaterial3D
		if sm == null:
			sm = StandardMaterial3D.new()
		if mode == "nometal":
			sm.metallic = 0.0
			sm.roughness = 1.0
			sm.metallic_texture = null
			sm.roughness_texture = null
		elif mode == "red":
			sm.albedo_texture = null
			sm.albedo_color = Color(0.72, 0.08, 0.08)
		return sm


	func _override(m: Material) -> void:
		for row in mesh_rows:
			var mi := row["mi"] as MeshInstance3D
			mi.set_surface_override_material(int(row["surface"]), m)


	func _process(_d: float) -> void:
		if busy:
			return
		busy = true
		if not initialized:
			initialized = true
			if not _init_layer():
				print("STACK_JSON " + JSON.stringify(
					{"error": "layer setup failed"}))
				get_tree().quit(1)
				return
		wait += 1
		if wait < WARM:
			busy = false
			return
		if stage == 0:
			await _snap("0-orig")
			for l in lights:
				(l as DirectionalLight3D).light_energy = 0.0
		elif stage == 1:
			await _snap("1-lights0")
			_restore_lights()
			_override(_variant("nometal"))
		elif stage == 2:
			await _snap("2-nometal")
			_override(_variant("red"))
		elif stage == 3:
			await _snap("3-redalbedo")
			# 还原一切运行时改动，只把相机 yaw 从 +55 切到 -55。
			# 这一帧用来判「白布青云纹是资产固有，还是只在正面视角可见」。
			_override(null)
			lf.set_view(-55.0, false)
		elif stage == 4:
			await _snap("4-neg55")
			var payload := {
				"shots": rows,
				"glb_path": String(lf.glb_path),
				"role": String(lf.role_id),
				"sv_size": [lf.sv.size.x, lf.sv.size.y],
				"yaw": lf.view_yaw_deg,
				"lights": lights.size(),
				"light_energy0": light_energy0,
				"mesh_rows": mesh_rows.size(),
				"material_slots": _material_slots(),
				"visual_state": lf.visual_state(),
			}
			print("STACK_JSON " + JSON.stringify(payload))
			get_tree().quit(0)
			return
		stage += 1
		wait = 0
		busy = false


func _init() -> void:
	var out_dir := OS.get_environment("STACK_OUT")
	if out_dir == "":
		print("STACK_JSON " + JSON.stringify({"error": "STACK_OUT missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var pp: Variant = JSON.parse_string(
		FileAccess.get_file_as_string("res://data/motion_input_foe.json"))
	var motion: Dictionary = {}
	if pp is Dictionary:
		motion = pp
	var d := Driver.new()
	d.out_dir = out_dir
	d.motion = motion
	root.add_child(d)
