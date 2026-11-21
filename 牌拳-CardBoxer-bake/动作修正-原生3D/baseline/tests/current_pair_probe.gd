extends SceneTree
## B 路线 P0：按用户实际运行路径取证当前两层各自渲染了什么。
##
## 完整 main.tscn + CARD_BOXER_3D=1（与 运行游戏-3D.bat 同一条接线），
## warm 后：
##   * 两层 SubViewport 的 ViewportTexture 各存一张原图；
##   * 读回每层实际 glb_path / role / yaw / mesh 名 / 顶点数 / albedo 路径；
##   * 另存一张 1280x720 整帧。
## 用于终结「独立 foe 层探针渲出纯重甲怪，历史 o-sv-foe.png 却有白布」的矛盾。
##
## 跑法：
##   CARD_BOXER_3D=1 PAIR_OUT=<abs> godot --path . --resolution 1280x720 \
##     --quit-after 900 --script res://tests/current_pair_probe.gd

const ArenaScene = preload("res://scenes/main.tscn")


class Driver:
	extends Node

	const WARM := 30
	var arena: Node2D
	var out_dir := ""
	var wait := 0
	var busy := false
	var done := false
	var rows: Array = []


	func _mesh_info(n: Node, acc: Array) -> void:
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
			_mesh_info(c, acc)


	func _layer_info(label: String, l) -> Dictionary:
		var out := {"label": label, "present": l != null}
		if l == null or l.sv == null:
			return out
		out["glb_path"] = String(l.glb_path)
		out["role"] = String(l.role_id)
		out["yaw"] = float(l.view_yaw_deg)
		out["flip"] = bool(l.view_flip)
		out["foe_visual"] = bool(l.foe_visual)
		var meshes: Array = []
		_mesh_info(l.sv, meshes)
		out["meshes"] = meshes
		var t = l.sv.get_texture()
		if t != null:
			var im = t.get_image()
			if im != null:
				var p := out_dir + "/pair-sv-" + label + ".png"
				out["sv_png"] = p
				out["sv_error"] = int(im.save_png(p))
				out["sv_size"] = [im.get_width(), im.get_height()]
		return out


	func _process(_d: float) -> void:
		if busy or done:
			return
		busy = true
		wait += 1
		if wait < WARM:
			busy = false
			return
		done = true
		arena.paused = true
		# paused 后 _sync_3d_layer 不跑，位置必须显式给（G 路线踩过）。
		if arena.layer_3d != null:
			arena.layer_3d.position = (arena.player.position
				+ arena.player.visual_shift)
		if arena.layer_3d_foe != null:
			arena.layer_3d_foe.position = (arena.enemy.position
				+ arena.enemy.visual_shift)
		await RenderingServer.frame_post_draw
		var full := get_viewport().get_texture().get_image()
		var fp := out_dir + "/pair-live.png"
		var ferr := int(full.save_png(fp))
		var payload := {
			"player": _layer_info("player", arena.layer_3d),
			"foe": _layer_info("foe", arena.layer_3d_foe),
			"full_frame": {"path": fp, "w": full.get_width(),
				"h": full.get_height(), "save_error": ferr},
			"use_3d": bool(arena.use_3d),
		}
		print("PAIR_JSON " + JSON.stringify(payload))
		get_tree().quit(0)


func _init() -> void:
	var out_dir := OS.get_environment("PAIR_OUT")
	if out_dir == "":
		print("PAIR_JSON " + JSON.stringify({"error": "PAIR_OUT missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var inst: Node2D = (ArenaScene as PackedScene).instantiate()
	root.add_child(inst)
	var d := Driver.new()
	d.arena = inst
	d.out_dir = out_dir
	root.add_child(d)
