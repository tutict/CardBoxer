extends SceneTree
## 逐帧胶片：把一张牌从头到尾的**游戏真实渲染**存成 PNG 序列。
##
## 用来做「同一张牌、同一帧号」的 A/B 对照：换掉 fighter.gd 再跑一次，
## 两边帧数完全相同，可以直接并排。
##
## 跑法（游戏目录下）：
##   CARD_BOXER_STRIP=uppercut CARD_BOXER_STRIP_DIR=<dir> godot --path . --resolution 1280x720 --script res://tests/motion_strip.gd
## 必须带窗口（headless 没有渲染目标）。帧数取自 card_data，跑完自动退出。

const Defs = preload("res://scripts/card_data.gd")
const FighterScript = preload("res://scripts/fighter.gd")


class Driver:
	extends Node
	var f: Node2D
	var out_dir := ""
	var total := 0
	var n := 0
	var busy := false

	func _process(_delta: float) -> void:
		if busy:
			return
		if n >= total:
			# 多存一帧：最后一帧停在收招后的静止姿态，肉眼比对需要它。
			busy = true
			await RenderingServer.frame_post_draw
			get_viewport().get_texture().get_image().save_png("%s/strip_%02d.png" % [out_dir, n])
			print("STRIP DONE %d frames -> %s" % [n, out_dir])
			get_tree().quit(0)
			return
		busy = true
		n += 1
		f.tick(Defs.FRAME, 0.0, true)
		f.queue_redraw()
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png("%s/strip_%02d.png" % [out_dir, n])
		busy = false


func _init() -> void:
	var card_id := OS.get_environment("CARD_BOXER_STRIP")
	var out_dir := OS.get_environment("CARD_BOXER_STRIP_DIR")
	if card_id == "" or out_dir == "":
		print("缺少 CARD_BOXER_STRIP / CARD_BOXER_STRIP_DIR")
		quit(1)
		return
	var card := Defs.card(card_id)
	if card.is_empty():
		print("没有这张牌: %s" % card_id)
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)

	var f: Node2D = FighterScript.new()
	f.is_player = true
	f.facing = 1
	f.meter = 5.0
	f.position = Vector2(640, 520)
	root.add_child(f)
	f.play_card(card_id)

	var d := Driver.new()
	d.f = f
	d.out_dir = out_dir
	d.total = int(card.get("windup", 4)) + int(card.get("active", 3)) + int(card.get("recover", 8))
	root.add_child(d)
	print("STRIP START %s, %d frames" % [card_id, d.total])
