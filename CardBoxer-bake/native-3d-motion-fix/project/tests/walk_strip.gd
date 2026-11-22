extends SceneTree
## 走路的逐帧胶片：固定机位、只让人往前走，用来看脚到底踩没踩住。
##
##   CARD_BOXER_WALK_DIR=<dir> godot --path . --resolution 1280x720 --script res://tests/walk_strip.gd
##   CARD_BOXER_WALK_DIR=<dir> CARD_BOXER_WALK_MOVE=-1 ...   # 倒着走（后退步）
##
## 机位不动，所以「支撑期的那只脚在第几列像素」应该纹丝不动 —— 那是肉眼的判据。

const Defs = preload("res://scripts/card_data.gd")
const FighterScript = preload("res://scripts/fighter.gd")


class Driver:
	extends Node
	var f: Node2D
	var out_dir := ""
	var move := 1.0
	var total := 36
	var n := 0
	var busy := false

	func _process(_delta: float) -> void:
		if busy:
			return
		busy = true
		f.tick(Defs.FRAME, move, true)
		f.queue_redraw()
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png("%s/walk_%02d.png" % [out_dir, n])
		n += 1
		busy = false
		if n > total:
			print("WALK DONE %d frames -> %s" % [n, out_dir])
			get_tree().quit(0)


func _init() -> void:
	var out_dir := OS.get_environment("CARD_BOXER_WALK_DIR")
	if out_dir == "":
		print("缺少 CARD_BOXER_WALK_DIR")
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var move := float(OS.get_environment("CARD_BOXER_WALK_MOVE").to_float() if OS.get_environment("CARD_BOXER_WALK_MOVE") != "" else "1.0")
	var total := int(OS.get_environment("CARD_BOXER_WALK_FRAMES").to_int() if OS.get_environment("CARD_BOXER_WALK_FRAMES") != "" else "36")

	var f: Node2D = FighterScript.new()
	f.is_player = true
	f.facing = 1
	f.position = Vector2(420, 520)
	root.add_child(f)

	var d := Driver.new()
	d.f = f
	d.out_dir = out_dir
	d.move = move
	d.total = total
	root.add_child(d)
	print("WALK START move=%.0f, %d frames" % [move, total])
