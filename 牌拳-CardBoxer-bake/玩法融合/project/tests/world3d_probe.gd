extends SceneTree
## B 路线 P0 终结探针：两个 SubViewport 是否共享 World3D 导致角色重叠。
##
## 完整 main.tscn + CARD_BOXER_3D=1，同进程两状态：
##   before  现状（两层各自 new SubViewport，未设 own_world_3d）
##   after   给两层 SubViewport 各设 own_world_3d=true
## 每状态分别存两层 SubViewport 原图 + 整帧，并读回 world_3d 的
## instance_id / own_world_3d，证明「共享」还是「独立」。
##
## 只读游戏资产；运行时改 Viewport 属性，不写回任何文件。
##
## 跑法：
##   CARD_BOXER_3D=1 W3D_OUT=<abs> godot --path . --resolution 1280x720 \
##     --quit-after 1200 --script res://tests/world3d_probe.gd

const ArenaScene = preload("res://scenes/main.tscn")


class Driver:
	extends Node

	const WARM := 30
	const SETTLE := 20
	var arena: Node2D
	var out_dir := ""
	var wait := 0
	var busy := false
	var stage := 0
	var initialized := false
	var rows: Array = []


	func _layers() -> Array:
		return [["player", arena.layer_3d],
				["foe", arena.layer_3d_foe]]


	func _state(tag: String) -> Dictionary:
		var out := {"tag": tag, "layers": []}
		for pair in _layers():
			var label: String = pair[0]
			var l = pair[1]
			var rec := {"label": label, "present": l != null}
			if l != null and l.sv != null:
				var w = l.sv.get("world_3d")
				rec["world3d_id"] = (int(w.get_instance_id())
					if w != null else 0)
				rec["own_world_3d"] = l.sv.get("own_world_3d")
				rec["yaw"] = float(l.view_yaw_deg)
				var t = l.sv.get_texture()
				if t != null:
					var im = t.get_image()
					if im != null:
						var p := (out_dir + "/w3d-" + tag + "-sv-"
							+ label + ".png")
						rec["sv_png"] = p
						rec["sv_error"] = int(im.save_png(p))
			out["layers"].append(rec)
		return out


	func _snap_full(tag: String) -> void:
		await RenderingServer.frame_post_draw
		var im := get_viewport().get_texture().get_image()
		var p := out_dir + "/w3d-" + tag + "-live.png"
		im.save_png(p)


	func _process(_d: float) -> void:
		if busy:
			return
		busy = true
		if not initialized:
			initialized = true
			arena.paused = true
			if arena.layer_3d != null:
				arena.layer_3d.position = (arena.player.position
					+ arena.player.visual_shift)
			if arena.layer_3d_foe != null:
				arena.layer_3d_foe.position = (arena.enemy.position
					+ arena.enemy.visual_shift)
		wait += 1
		if wait < (WARM if stage == 0 else SETTLE):
			busy = false
			return
		if stage == 0:
			rows.append(_state("before"))
			await _snap_full("before")
			for pair in _layers():
				var l = pair[1]
				if l != null and l.sv != null:
					# 用 Object.set 动态设，属性名不对照返回 false 而不是崩。
					l.sv.set("own_world_3d", true)
					var w := World3D.new()
					l.sv.set("world_3d", w)
			stage = 1
		elif stage == 1:
			rows.append(_state("after"))
			await _snap_full("after")
			var payload := {"states": rows,
				"use_3d": bool(arena.use_3d)}
			print("W3D_JSON " + JSON.stringify(payload))
			get_tree().quit(0)
			return
		wait = 0
		busy = false


func _init() -> void:
	var out_dir := OS.get_environment("W3D_OUT")
	if out_dir == "":
		print("W3D_JSON " + JSON.stringify({"error": "W3D_OUT missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var inst: Node2D = (ArenaScene as PackedScene).instantiate()
	root.add_child(inst)
	var d := Driver.new()
	d.arena = inst
	d.out_dir = out_dir
	root.add_child(d)
