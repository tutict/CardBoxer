extends SceneTree
## I 路线：证明 CARD_BOXER_FOE_VISUAL=none 真的让 foe 层退回 H 原样。
##
## 同进程同树五帧（跨进程整帧像素等价已退役，见 H 路线记录）：
##   base     = 无 3D 层（纯背景，用来造角色掩膜）
##   off1     = 挂两层，env=none，configure("foe") 不得启用视觉层
##   off2     = 同状态再截一帧（零操作对照）
##   forced   = 手动 set_foe_visual(true)，证明本进程视觉层功能完好
##   restored = set_foe_visual(false)，证明能逐像素还原到 off1
##
## 跑法（必须带窗口）：
##   CARD_BOXER_FOE_VISUAL=none I_OFF_DIR=<abs> godot --path . \
##     --resolution 1280x720 --quit-after 900 \
##     --script res://tests/off_switch_probe.gd

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
	var states: Array = []
	var player_ready := false
	var foe_ready := false
	var foe_initial_visual := true

	func _snap(name: String) -> void:
		await RenderingServer.frame_post_draw
		var img := get_viewport().get_texture().get_image()
		var path := out_dir + "/off-" + name + ".png"
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
		foe_initial_visual = bool(lf.visual_state().get("foe_visual", true))

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
			_record_state("off1")
		elif stage == 1:
			await _snap("off1")
		elif stage == 2:
			await _snap("off2")
			arena.layer_3d_foe.set_foe_visual(true)
			_record_state("forced")
		elif stage == 3:
			await _snap("forced")
			arena.layer_3d_foe.set_foe_visual(false)
			_record_state("restored")
		elif stage == 4:
			await _snap("restored")
			var payload := {
				"shots": rows, "states": states,
				"player_layer_ready": player_ready,
				"foe_layer_ready": foe_ready,
				"foe_initial_visual": foe_initial_visual,
				"player_visual_state": arena.layer_3d.visual_state()
						if arena.layer_3d != null else {},
				"env_visual_none": OS.get_environment(
						"CARD_BOXER_FOE_VISUAL"),
			}
			var f := FileAccess.open(out_dir + "/off_result.json",
					FileAccess.WRITE)
			if f != null:
				f.store_string(JSON.stringify(payload, "\t"))
				f.close()
			print("IOFF_JSON " + JSON.stringify(payload))
			get_tree().quit(0)
			return
		stage += 1
		busy = false


func _init() -> void:
	var out_dir := OS.get_environment("I_OFF_DIR")
	if out_dir == "":
		print("IOFF_JSON " + JSON.stringify({"error": "I_OFF_DIR missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var inst: Node2D = (ArenaScene as PackedScene).instantiate()
	root.add_child(inst)
	var d := Driver.new()
	d.arena = inst
	d.out_dir = out_dir
	root.add_child(d)
	print("IOFF_START out=%s" % out_dir)
