extends SceneTree
## H 路线诊断：同一进程内隐藏单层，判定两个 SubViewport 是否串味。
##
## 跨进程逐像素对比不成立（全局 RNG 每次启动随机化）。这里在同一个
## 进程、同一棵树里抓 4 帧：both / player-hidden / foe-hidden / neither。
## 若隐藏 player 时右侧 ROI 也变了，就说明两个视口内容互相依赖。
##
## 跑法（必须带窗口）：
##   H_VP_DIR=<abs> godot --path . --resolution 1280x720 \
##     --quit-after 900 --script res://tests/vp_diag_probe.gd

const ArenaScene = preload("res://scenes/main.tscn")
const LayerScript = preload("res://scripts/fighter_3d_layer.gd")


class Driver:
	extends Node

	const LayerScript = preload("res://scripts/fighter_3d_layer.gd")
	const MOTION_P := "res://data/motion_input.json"
	const MOTION_F := "res://data/motion_input_foe.json"
	const WARM := 20
	const NAMES := ["off", "both", "player-hidden", "foe-hidden", "neither"]

	var arena: Node2D
	var out_dir := ""
	var motion_p: Dictionary = {}
	var motion_f: Dictionary = {}
	var initialized := false
	var busy := false
	var stage := 0
	var wait := 0
	var rows: Array = []
	var player_ready := false
	var foe_ready := false

	func _snap(name: String) -> void:
		await RenderingServer.frame_post_draw
		var img := get_viewport().get_texture().get_image()
		var path := out_dir + "/vp-" + name + ".png"
		var err := img.save_png(path)
		rows.append({"name": name, "path": path,
			"w": img.get_width(), "h": img.get_height(),
			"save_error": int(err)})

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

	func _set_vis(p: bool, f: bool) -> void:
		if arena.layer_3d != null:
			arena.layer_3d.visible = p
		if arena.layer_3d_foe != null:
			arena.layer_3d_foe.visible = f

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
			await _snap("off")
			_attach()
		elif stage == 1:
			await _snap("both")
			_set_vis(false, true)
		elif stage == 2:
			await _snap("player-hidden")
			_set_vis(true, false)
		elif stage == 3:
			await _snap("foe-hidden")
			_set_vis(false, false)
		elif stage == 4:
			await _snap("neither")
			var payload := {
				"shots": rows,
				"player_layer_ready": player_ready,
				"foe_layer_ready": foe_ready,
				"player_glb": String(arena.layer_3d.glb_path)
						if arena.layer_3d != null else "",
				"foe_glb": String(arena.layer_3d_foe.glb_path)
						if arena.layer_3d_foe != null else "",
			}
			var f := FileAccess.open(out_dir + "/vp_result.json",
					FileAccess.WRITE)
			if f != null:
				f.store_string(JSON.stringify(payload, "\t"))
				f.close()
			print("HVP_JSON " + JSON.stringify(payload))
			get_tree().quit(0)
			return
		stage += 1
		busy = false


func _init() -> void:
	var out_dir := OS.get_environment("H_VP_DIR")
	if out_dir == "":
		print("HVP_JSON " + JSON.stringify({"error": "H_VP_DIR missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var inst: Node2D = (ArenaScene as PackedScene).instantiate()
	root.add_child(inst)
	var d := Driver.new()
	d.arena = inst
	d.out_dir = out_dir
	root.add_child(d)
	print("HVP_START out=%s" % out_dir)
