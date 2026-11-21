extends SceneTree
## I 路线诊断：on/plain 两态里，两个 SubViewport 的灯能量各是多少。
## 用来判定「玩家侧跟着变暗」是代码 bug 还是多 SubViewport 光照串扰。
## 跑法：godot --path . --resolution 1280x720 --quit-after 900 \
##        --script res://tests/light_isolation_probe.gd

const ArenaScene = preload("res://scenes/main.tscn")


class Driver:
	extends Node

	const LayerScript = preload("res://scripts/fighter_3d_layer.gd")
	const MOTION_P := "res://data/motion_input.json"
	const MOTION_F := "res://data/motion_input_foe.json"
	const WARM := 20

	var arena: Node2D
	var stage := 0
	var wait := 0
	var busy := false
	var initialized := false
	var rows: Array = []

	func _lights(layer) -> Array:
		var out: Array = []
		if layer == null or layer.sv == null:
			return out
		for c in layer.sv.get_children():
			if c is DirectionalLight3D:
				var l := c as DirectionalLight3D
				out.append({"energy": snappedf(l.light_energy, 0.0001),
					"r": snappedf(l.light_color.r, 0.0001),
					"g": snappedf(l.light_color.g, 0.0001),
					"b": snappedf(l.light_color.b, 0.0001)})
		return out

	func _overrides(layer) -> int:
		var n := 0
		if layer == null:
			return n
		for row in layer._mesh_rows:
			var mi: MeshInstance3D = row["mi"]
			if mi.get_surface_override_material(int(row["surface"])) != null:
				n += 1
		return n

	func _attach() -> void:
		var lp := LayerScript.new()
		arena.world.add_child(lp)
		if lp.setup(JSON.parse_string(
				FileAccess.get_file_as_string(MOTION_P))):
			arena.layer_3d = lp
			lp.position = arena.player.position + arena.player.visual_shift
			arena.player.draw_3d_override = true
		var lf := LayerScript.new()
		lf.configure("foe", LayerScript.FOE_GLB_PATH,
				LayerScript.DEFAULT_FOE_YAW, false)
		arena.world.add_child(lf)
		if lf.setup(JSON.parse_string(
				FileAccess.get_file_as_string(MOTION_F))):
			arena.layer_3d_foe = lf
			lf.position = arena.enemy.position + arena.enemy.visual_shift
			arena.enemy.draw_3d_override = true

	func _record(tag: String) -> void:
		rows.append({
			"tag": tag,
			"player_lights": _lights(arena.layer_3d),
			"foe_lights": _lights(arena.layer_3d_foe),
			"player_overrides": _overrides(arena.layer_3d),
			"foe_overrides": _overrides(arena.layer_3d_foe),
			"player_state": arena.layer_3d.visual_state()
					if arena.layer_3d != null else {},
			"foe_state": arena.layer_3d_foe.visual_state()
					if arena.layer_3d_foe != null else {},
		})

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
		wait += 1
		if wait < WARM:
			busy = false
			return
		wait = 0
		if stage == 0:
			_attach()
			_record("on")
		elif stage == 1:
			arena.layer_3d_foe.set_foe_visual(false)
			_record("plain")
		elif stage == 2:
			arena.layer_3d_foe.set_foe_visual(true)
			_record("again")
			print("ILIGHT_JSON " + JSON.stringify({"rows": rows}))
			get_tree().quit(0)
			return
		stage += 1
		busy = false


func _init() -> void:
	var inst: Node2D = (ArenaScene as PackedScene).instantiate()
	root.add_child(inst)
	var d := Driver.new()
	d.arena = inst
	root.add_child(d)
