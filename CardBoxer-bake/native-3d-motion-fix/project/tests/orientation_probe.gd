extends SceneTree
## 朝向诊断：同进程同树，一次只改一侧的 yaw / flip，其余恒定。
## 每帧额外把两层 SubViewport 原图单独存盘，用来区分「资产本身就叠着
## 两套造型」与「2D 合成把同一层画了两遍」。
##
## 跑法（必须带窗口 + 打开 3D）：
##   CARD_BOXER_3D=1 ORIENT_DIR=<abs> godot --path . --resolution 1280x720 \
##     --quit-after 1200 --script res://tests/orientation_probe.gd

const ArenaScene = preload("res://scenes/main.tscn")


class Driver:
	extends Node

	const WARM := 24
	const SETTLE := 10
	const BASE_P_YAW := 55.0
	const BASE_P_FLIP := false
	const BASE_F_YAW := -55.0
	const BASE_F_FLIP := false
	# 一次只动一侧：p-* 扫玩家，f-* 扫对手；其余一律回默认。
	const COMBOS := [
		{"name": "p-y55-f0", "who": "player", "yaw": 55.0, "flip": false},
		{"name": "p-y55-f1", "who": "player", "yaw": 55.0, "flip": true},
		{"name": "p-yn55-f0", "who": "player", "yaw": -55.0, "flip": false},
		{"name": "p-yn55-f1", "who": "player", "yaw": -55.0, "flip": true},
		{"name": "f-yn55-f0", "who": "foe", "yaw": -55.0, "flip": false},
		{"name": "f-yn55-f1", "who": "foe", "yaw": -55.0, "flip": true},
		{"name": "f-y55-f0", "who": "foe", "yaw": 55.0, "flip": false},
		{"name": "f-y55-f1", "who": "foe", "yaw": 55.0, "flip": true},
	]

	var arena: Node2D
	var out_dir := ""
	var wait := 0
	var busy := false
	var stage := 0
	var rows: Array = []

	func _snap(name: String) -> void:
		await RenderingServer.frame_post_draw
		var img := get_viewport().get_texture().get_image()
		var path := out_dir + "/o-" + name + ".png"
		var err := img.save_png(path)
		rows.append({
			"name": name, "path": path,
			"w": img.get_width(), "h": img.get_height(),
			"save_error": int(err),
			"p_yaw": float(arena.layer_3d.view_yaw_deg),
			"p_flip": bool(arena.layer_3d.view_flip),
			"f_yaw": float(arena.layer_3d_foe.view_yaw_deg),
			"f_flip": bool(arena.layer_3d_foe.view_flip),
		})

	func _sv_dump() -> void:
		for pair in [["player", arena.layer_3d],
				["foe", arena.layer_3d_foe]]:
			var l = pair[1]
			if l == null or l.sv == null:
				continue
			var t = l.sv.get_texture()
			if t == null:
				continue
			var im = t.get_image()
			if im != null:
				im.save_png(out_dir + "/o-sv-" + String(pair[0]) + ".png")

	func _reset_base() -> void:
		arena.layer_3d.set_view(BASE_P_YAW, BASE_P_FLIP)
		arena.layer_3d_foe.set_view(BASE_F_YAW, BASE_F_FLIP)

	func _apply_combo(i: int) -> void:
		var s: Dictionary = COMBOS[i]
		var l = (arena.layer_3d if String(s["who"]) == "player"
				else arena.layer_3d_foe)
		l.set_view(float(s["yaw"]), bool(s["flip"]))

	func _process(_d: float) -> void:
		if busy:
			return
		busy = true
		if stage == 0:
			wait += 1
			if wait >= WARM:
				arena.paused = true
				# paused 后 _sync_3d_layer() 不跑，位置必须显式给，
				# 否则两层留在 (0,0) 被画到画布外（G 路线首版踩过）。
				arena.layer_3d.position = (arena.player.position
						+ arena.player.visual_shift)
				arena.layer_3d_foe.position = (arena.enemy.position
						+ arena.enemy.visual_shift)
				_sv_dump()
				await _snap("base")
				_apply_combo(0)
				stage = 1
				wait = 0
		elif stage <= COMBOS.size():
			wait += 1
			if wait >= SETTLE:
				var spec: Dictionary = COMBOS[stage - 1]
				await _snap(String(spec["name"]))
				if stage < COMBOS.size():
					_reset_base()
					_apply_combo(stage)
				stage += 1
				wait = 0
		else:
			var payload := {
				"shots": rows,
				"combos": COMBOS,
				"base": {"p_yaw": BASE_P_YAW, "p_flip": BASE_P_FLIP,
					"f_yaw": BASE_F_YAW, "f_flip": BASE_F_FLIP},
				"glb_player": String(arena.layer_3d.glb_path),
				"glb_foe": String(arena.layer_3d_foe.glb_path),
			}
			var f := FileAccess.open(out_dir + "/o_result.json",
					FileAccess.WRITE)
			if f != null:
				f.store_string(JSON.stringify(payload, "\t"))
				f.close()
			print("ORIENT_JSON " + JSON.stringify(payload))
			get_tree().quit(0)
			return
		busy = false


func _init() -> void:
	var out_dir := OS.get_environment("ORIENT_DIR")
	if out_dir == "":
		print("ORIENT_JSON " + JSON.stringify({"error": "ORIENT_DIR missing"}))
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_dir)
	var inst: Node2D = (ArenaScene as PackedScene).instantiate()
	root.add_child(inst)
	var d := Driver.new()
	d.arena = inst
	d.out_dir = out_dir
	root.add_child(d)
	print("ORIENT_START out=%s" % out_dir)
