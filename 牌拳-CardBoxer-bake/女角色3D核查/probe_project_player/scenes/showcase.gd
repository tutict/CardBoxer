extends Node3D
## 女角色 3D 展示场景：隐藏 Voxel 代理壳，只显示带 4096² PBR 的高模。
## 代理壳本来是驱动用的中间层，跟高模几乎同形、共材质，两层同时可见会
## 出现 z-fighting / 溶蚀灰壳，看起来像「另一个怪物」，必须关掉。

func _ready() -> void:
	var cam := get_node_or_null("Camera3D") as Camera3D
	if cam != null:
		cam.look_at(Vector3(0.0, 0.86, 0.0), Vector3.UP)

	var hidden := 0
	for m in find_children("*", "MeshInstance3D", true, false):
		if String(m.name) == "e_continuous_shell":
			(m as MeshInstance3D).visible = false
			hidden += 1
	print("SHOWCASE_READY hidden_proxy_shell=" + str(hidden) +
			" camera=" + (cam.name if cam != null else "NONE"))

	var we := WorldEnvironment.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.075, 0.090, 0.125)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.42, 0.48, 0.62)
	env.ambient_light_energy = 0.68
	we.environment = env
	add_child(we)

	var ground := get_node_or_null("Ground") as MeshInstance3D
	if ground != null:
		var plane := PlaneMesh.new()
		plane.size = Vector2(12.0, 12.0)
		ground.mesh = plane
		var mat := StandardMaterial3D.new()
		mat.albedo_color = Color(0.10, 0.12, 0.16)
		mat.roughness = 0.95
		ground.material_override = mat
