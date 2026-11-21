extends SceneTree
## World3D 接线修复 P1：最小改动口径探针。
##
## 一次进程只跑一个 mode（由 W3D_MIN_MODE 指定），避免运行时切换 world
## 留下残留，也避免多视口同帧取图的口径问题：
##   none  现状，两层都不设任何 world 属性
##   own   只设 own_world_3d = true
##   world 只设 world_3d = World3D.new()
##   both  两者都设（B 路线 P0 探针口径）
## 完整 main.tscn + CARD_BOXER_3D=1，首帧就设置（等价于落地在 setup() 里），
## 稳定后读回 world_3d 的 instance_id / own_world_3d，并各存两层
## SubViewport 原图 + 整帧。
##
## 只读游戏资产；运行时改 Viewport 属性，不写回任何文件。
##
## 跑法：
##   CARD_BOXER_3D=1 W3D_MIN_OUT=<abs> W3D_MIN_MODE=own \
##     godot --path . --resolution 1280x720 --quit-after 1200 \
##     --script res://tests/world3d_min_probe.gd

const ArenaScene = preload("res://scenes/main.tscn")


class Driver:
	extends Node

	const WARM := 60
	var arena: Node2D
	var out_dir := ""
	var mode := "none"
	var wait := 0
	var initialized := false
	var done := false
	var apply_rows: Array = []


	func _layers() -> Array:
		return [["player", arena.layer_3d],
				["foe", arena.layer_3d_foe]]


	func _apply() -> void:
		for pair in _layers():
			var label: String = pair[0]
			var l = pair[1]
			var rec := {"label": label, "present": l != null,
					"mode": mode}
			if l != null and l.sv != null:
				# none 组显式关掉，保证源码落地 own_world_3d=true 之后
				# 仍能复算「共享 world」的旧状态对照。
				if mode == "none":
					l.sv.set("own_world_3d", false)
				if mode == "own" or mode == "both":
					l.sv.set("own_world_3d", true)
				if mode == "world" or mode == "both":
					var w := World3D.new()
					l.sv.set("world_3d", w)
				# 读回设置后的状态，不依赖 Object.set 的返回值口径。
				rec["own_after_apply"] = l.sv.get("own_world_3d")
				var wa = l.sv.get("world_3d")
				rec["world_id_after_apply"] = (int(wa.get_instance_id())
					if wa != null else 0)
			apply_rows.append(rec)


	func _state() -> Dictionary:
		var out := {"layers": []}
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
						var p := (out_dir + "/min-" + mode + "-sv-"
							+ label + ".png")
						rec["sv_png"] = p
						rec["sv_error"] = int(im.save_png(p))
			out["layers"].append(rec)
		return out


	func _snap_full() -> void:
		await RenderingServer.frame_post_draw
		var im := get_viewport().get_texture().get_image()
		var p := out_dir + "/min-" + mode + "-live.png"
		im.save_png(p)


	func _process(_d: float) -> void:
		if done:
			return
		if not initialized:
			initialized = true
			arena.paused = true
			if arena.layer_3d != null:
				arena.layer_3d.position = (arena.player.position
					+ arena.player.visual_shift)
			if arena.layer_3d_foe != null:
				arena.layer_3d_foe.position = (arena.enemy.position
					+ arena.enemy.visual_shift)
			_apply()
		wait += 1
		if wait < WARM:
			return
		done = true
		var st := _state()
		await _snap_full()
		var payload := {"mode": mode, "state": st,
				"apply_rows": apply_rows,
				"use_3d": bool(arena.use_3d),
				"live_png": out_dir + "/min-" + mode + "-live.png"}
		print("W3D_MIN_JSON " + JSON.stringify(payload))
		get_tree().quit(0)


func _init() -> void:
	var out_dir := OS.get_environment("W3D_MIN_OUT")
	if out_dir == "":
		print("W3D_MIN_JSON " + JSON.stringify(
				{"error": "W3D_MIN_OUT missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var inst: Node2D = (ArenaScene as PackedScene).instantiate()
	root.add_child(inst)
	var d := Driver.new()
	d.arena = inst
	d.out_dir = out_dir
	d.mode = OS.get_environment("W3D_MIN_MODE")
	root.add_child(d)
