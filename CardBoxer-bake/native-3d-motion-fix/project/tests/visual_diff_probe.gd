extends SceneTree
## I 路线：同进程同树 A/B，证明「对手侧视觉区分」生效且玩家侧零变化。
##
## 四帧（都在同一进程、同一棵树）：
##   base  = 无 3D 层（纯背景，用来造角色掩膜）
##   on    = 两层 + foe 视觉启用
##   plain = set_foe_visual(false)（H 路线原样）
##   again = set_foe_visual(true)（可反复切换 / 还原）
## 跨进程整帧像素等价不成立（RNG 随机化），所以 A/B 必须同进程。
##
## 跑法（必须带窗口）：
##   I_VIS_DIR=<abs> godot --path . --resolution 1280x720 \
##     --quit-after 900 --script res://tests/visual_diff_probe.gd

const ArenaScene = preload("res://scenes/main.tscn")


class Driver:
	extends Node

	const LayerScript = preload("res://scripts/fighter_3d_layer.gd")
	const MOTION_P := "res://data/motion_input.json"
	const MOTION_F := "res://data/motion_input_foe.json"
	const WARM := 20
	const NAMES := ["base", "on", "on-repeat", "plain", "again"]

	var arena: Node2D
	var out_dir := ""
	var motion_p: Dictionary = {}
	var motion_f: Dictionary = {}
	var initialized := false
	var busy := false
	var stage := 0
	var wait := 0
	var rows: Array = []
	var states: Array = []
	var player_ready := false
	var foe_ready := false

	func _snap(name: String) -> void:
		await RenderingServer.frame_post_draw
		var img := get_viewport().get_texture().get_image()
		var path := out_dir + "/vis-" + name + ".png"
		var err := img.save_png(path)
		var vp := RenderingServer.get_rendering_info(
			RenderingServer.RENDERING_INFO_TOTAL_PRIMITIVES_IN_FRAME)
		var dc := RenderingServer.get_rendering_info(
			RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME)
		rows.append({"name": name, "path": path,
			"w": img.get_width(), "h": img.get_height(),
			"save_error": int(err), "prims": float(vp),
			"draw_calls": float(dc)})

	func _attach() -> void:
		var lp := LayerScript.new()
		arena.world.add_child(lp)
		player_ready = lp.setup(motion_p)
		if player_ready:
			arena.layer_3d = lp
			arena.motion_3d = motion_p
			lp.position = arena.player.position + arena.player.visual_shift
			arena.player.draw_3d_override = true
			arena.player.queue_redraw()
		var lf := LayerScript.new()
		lf.configure("foe", LayerScript.FOE_GLB_PATH,
				LayerScript.DEFAULT_FOE_YAW, false)
		arena.world.add_child(lf)
		foe_ready = lf.setup(motion_f)
		if foe_ready:
			arena.layer_3d_foe = lf
			arena.motion_3d_foe = motion_f
			lf.position = arena.enemy.position + arena.enemy.visual_shift
			arena.enemy.draw_3d_override = true
			arena.enemy.queue_redraw()

	func _record_state(tag: String) -> void:
		var s := {}
		if arena.layer_3d_foe != null:
			s = arena.layer_3d_foe.visual_state()
		s["tag"] = tag
		states.append(s)

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
			_attach()
			_record_state("on")
		elif stage == 1:
			await _snap("on")
			# 零操作对照：同状态再截一帧，区分帧间抖动与真串扰。
		elif stage == 2:
			await _snap("on-repeat")
			arena.layer_3d_foe.set_foe_visual(false)
			_record_state("plain")
		elif stage == 3:
			await _snap("plain")
			arena.layer_3d_foe.set_foe_visual(true)
			_record_state("again")
		elif stage == 4:
			await _snap("again")
			var payload := {
				"shots": rows, "states": states,
				"player_layer_ready": player_ready,
				"foe_layer_ready": foe_ready,
				"player_visual_state": arena.layer_3d.visual_state()
						if arena.layer_3d != null else {},
				"env_visual_none": OS.get_environment(
						"CARD_BOXER_FOE_VISUAL"),
			}
			var f := FileAccess.open(out_dir + "/vis_result.json",
					FileAccess.WRITE)
			if f != null:
				f.store_string(JSON.stringify(payload, "\t"))
				f.close()
			print("IVIS_JSON " + JSON.stringify(payload))
			get_tree().quit(0)
			return
		stage += 1
		busy = false


func _init() -> void:
	var out_dir := OS.get_environment("I_VIS_DIR")
	if out_dir == "":
		print("IVIS_JSON " + JSON.stringify({"error": "I_VIS_DIR missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var inst: Node2D = (ArenaScene as PackedScene).instantiate()
	root.add_child(inst)
	var d := Driver.new()
	d.arena = inst
	d.out_dir = out_dir
	root.add_child(d)
	print("IVIS_START out=%s" % out_dir)
