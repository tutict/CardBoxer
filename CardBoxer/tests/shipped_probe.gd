extends SceneTree
## World3D 接线修复 · 落地态验收探针（两个独立进程各跑一个 mode）。
##
##   shipped  CARD_BOXER_3D=1，探针不改任何运行时属性 → 真实落生态
##   legacy   CARD_BOXER_3D=1，首帧强制 own_world_3d=false → 复现旧 bug
##
## shipped 组是「零改动」的：不 set 任何 Viewport 属性、不隐藏 HUD / fx /
## World，只截整帧 + 两层 SubViewport 原图，并读回 own_world_3d / yaw /
## flip / visual_state()，用来证明游戏里真的已经分开，而不是探针造出来的。
## 默认关（不带 CARD_BOXER_3D）由 runner 另用 display_stopgap_probe.gd 跑，
## 因为那个探针的 payload 带 use_3d / override / yaw 读回字段。
##
## 跑法：SHIPPED_OUT=<abs> SHIPPED_MODE=shipped godot --path . \
##   --resolution 1280x720 --quit-after 1200 --script res://tests/shipped_probe.gd

const ArenaScene = preload("res://scenes/main.tscn")


class Driver:
	extends Node

	const WARM := 60
	var arena: Node2D
	var out_dir := ""
	var mode := "shipped"
	var wait := 0
	var initialized := false
	var done := false


	func _layers() -> Array:
		return [["player", arena.layer_3d],
				["foe", arena.layer_3d_foe]]


	func _state() -> Dictionary:
		var out := {"layers": []}
		for pair in _layers():
			var label: String = pair[0]
			var l = pair[1]
			var rec := {"label": label, "present": l != null}
			if l != null:
				rec["yaw"] = float(l.view_yaw_deg)
				rec["flip"] = bool(l.view_flip)
				rec["visual_state"] = l.visual_state()
				if l.sv != null:
					var w = l.sv.get("world_3d")
					rec["world3d_id"] = (int(w.get_instance_id())
						if w != null else 0)
					rec["own_world_3d"] = l.sv.get("own_world_3d")
					var t = l.sv.get_texture()
					if t != null:
						var im = t.get_image()
						if im != null:
							var p := (out_dir + "/sh-" + mode + "-sv-"
								+ label + ".png")
							rec["sv_png"] = p
							rec["sv_error"] = int(im.save_png(p))
			out["layers"].append(rec)
		return out


	func _snap_full() -> void:
		await RenderingServer.frame_post_draw
		var im := get_viewport().get_texture().get_image()
		var p := out_dir + "/sh-" + mode + "-live.png"
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
			if mode == "legacy":
				for pair in _layers():
					var l = pair[1]
					if l != null and l.sv != null:
						l.sv.set("own_world_3d", false)
		wait += 1
		if wait < WARM:
			return
		done = true
		var st := _state()
		await _snap_full()
		var payload := {"mode": mode, "state": st,
				"use_3d": bool(arena.use_3d),
				"env_3d": OS.get_environment("CARD_BOXER_3D"),
				"player_override": bool(arena.player.draw_3d_override),
				"enemy_override": bool(arena.enemy.draw_3d_override),
				"tk_phase": String(arena.tk_phase),
				"live_png": out_dir + "/sh-" + mode + "-live.png"}
		print("SHIPPED_JSON " + JSON.stringify(payload))
		get_tree().quit(0)


func _init() -> void:
	var out_dir := OS.get_environment("SHIPPED_OUT")
	if out_dir == "":
		print("SHIPPED_JSON " + JSON.stringify(
				{"error": "SHIPPED_OUT missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var inst: Node2D = (ArenaScene as PackedScene).instantiate()
	root.add_child(inst)
	var d := Driver.new()
	d.arena = inst
	d.out_dir = out_dir
	d.mode = OS.get_environment("SHIPPED_MODE")
	root.add_child(d)
