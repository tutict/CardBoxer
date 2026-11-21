extends SceneTree
## 止损探针：完整主场景（不隐藏 HUD / fx / World），截真实运行画面。
## 与 J/H 探针的区别：那两个会隐藏 HUD 并冻结，只留 World；这里保留全部，
## 用来判断用户反馈的「火柴人 + 乱码」到底出现在哪一层。
##
## 跑法（必须带窗口）：
##   DISPLAY_DIR=<abs> godot --path . --resolution 1280x720 \
##     --quit-after 900 --script res://tests/display_stopgap_probe.gd

const ArenaScene = preload("res://scenes/main.tscn")


class Driver:
	extends Node

	const WARM := 120

	var arena: Node2D
	var out_dir := ""
	var wait := 0
	var busy := false
	var stage := 0
	var rows: Array = []

	func _snap(name: String) -> void:
		await RenderingServer.frame_post_draw
		var img := get_viewport().get_texture().get_image()
		var path := out_dir + "/display-" + name + ".png"
		var err := img.save_png(path)
		rows.append({"name": name, "path": path,
			"w": img.get_width(), "h": img.get_height(),
			"save_error": int(err)})

	func _process(_d: float) -> void:
		if busy:
			return
		busy = true
		wait += 1
		if stage == 0 and wait >= WARM:
			await _snap("live")
			# 冻结后再截一帧：区分「动画瞬间的花屏」与「稳定存在的乱码」
			arena.paused = true
			wait = 0
			stage = 1
		elif stage == 1 and wait >= 12:
			await _snap("frozen")
			var payload := {
				"shots": rows,
				"use_3d": bool(arena.use_3d),
				"env_3d": OS.get_environment("CARD_BOXER_3D"),
				"layer_3d": arena.layer_3d != null,
				"layer_3d_foe": arena.layer_3d_foe != null,
				"player_override": bool(arena.player.draw_3d_override),
				"enemy_override": bool(arena.enemy.draw_3d_override),
				# 朝向订正验收：把运行时真实 yaw / flip 读回，
				# 不靠源码常量猜「改了没有」。
				"p_yaw": float(arena.layer_3d.view_yaw_deg)
						if arena.layer_3d != null else 0.0,
				"p_flip": bool(arena.layer_3d.view_flip)
						if arena.layer_3d != null else false,
				"f_yaw": float(arena.layer_3d_foe.view_yaw_deg)
						if arena.layer_3d_foe != null else 0.0,
				"f_flip": bool(arena.layer_3d_foe.view_flip)
						if arena.layer_3d_foe != null else false,
				"tk_phase": String(arena.tk_phase),
			}
			print("DISPLAY_JSON " + JSON.stringify(payload))
			get_tree().quit(0)
			return
		busy = false


func _init() -> void:
	var out_dir := OS.get_environment("DISPLAY_DIR")
	if out_dir == "":
		print("DISPLAY_JSON " + JSON.stringify({"error": "DISPLAY_DIR missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var inst: Node2D = (ArenaScene as PackedScene).instantiate()
	root.add_child(inst)
	var d := Driver.new()
	d.arena = inst
	d.out_dir = out_dir
	root.add_child(d)
	print("DISPLAY_START out=%s" % out_dir)
