extends SceneTree
const Rules = preload("res://scripts/tactical_rules.gd")
const Defs = preload("res://scripts/tactical_defs.gd")
const Match = preload("res://scripts/tactical_match.gd")
const Arena = preload("res://scripts/arena.gd")
var failures: Array = []
func expect(ok: bool, label: String) -> void:
	if not ok: failures.append(label)
func hits(r: Dictionary) -> Array:
	var found: Array = []
	for beat in r.events:
		for group in beat.groups:
			found.append_array(group.hits)
	return found
func _initialize() -> void:
	call_deferred("run")
func run() -> void:
	var c = Rules.default_context()
	c.player.jokers = ["shadow","opening","wind"]
	var r = Rules.resolve_exchange(["guard","guard","sidestep"],["guard","guard","uppercut"],c)
	expect(r.next_state.player.dodge_charge and r.next_state.foe.exposed,"third beat shadow/opening survives")
	var r2 = Rules.resolve_exchange(["jab","guard","guard"],["jab","guard","guard"],r.next_state)
	expect(hits(r2)[0].kind == "punish" and hits(r2)[0].damage == 14,"third beat shadow consumed in next turn")
	c = Rules.default_context()
	var f = Rules.resolve_exchange(["guard","guard","focus"],["guard","guard","guard"],c)
	expect(f.next_state.player.focus,"third beat focus survives")
	c = Rules.default_context()
	c.player.jokers = ["pressure"]
	var p = Rules.resolve_exchange(["guard","guard","jab"],["guard","guard","uppercut"],c)
	expect(p.next_state.player.tempo == 2,"third beat pressure survives")
	var m = Match.new(41)
	m.state = p.next_state
	m._new_round()
	expect(not m.state.player.focus and not m.state.player.dodge_charge and m.state.player.tempo == 0 and not m.state.foe.exposed,"new round clears temporary states")
	OS.set_environment("CARD_BOXER_BATTLE_MODE","tactical")
	OS.set_environment("CARD_BOXER_3D","1")
	var a = Arena.new()
	root.add_child(a)
	a.set_process(false)
	a.hud.set_process(false)
	await process_frame
	for id in ["jab","cross","uppercut","sweep","throw","guard_break","armored_heavy","pursuit"]:
		a._start_tactical_match()
		m = a.tactical
		m.state.distance = 0
		m.player_plan = [id,"guard","focus"]
		m.enemy_plan = ["guard","guard","focus"]
		m._begin_resolve()
		var time = Match.START_S+float(m.active_beat.actions.player.start)*Match.FRAME_S
		a._process(time)
		var pv = a.last_visuals.player
		var ev = a.last_visuals.foe
		var anchor = "rear_hand" if id in ["cross","guard_break"] else "lead_hand"
		var fist = a.player.position+pv.canvas_shift+a.layer_3d.anchor_offset(pv.pose,anchor,1,pv.canvas_tilt)
		var head = a.enemy.position+ev.canvas_shift+a.layer_3d_foe.anchor_offset(ev.pose,"head",-1,ev.canvas_tilt)
		var chest = a.enemy.position+ev.canvas_shift+a.layer_3d_foe.anchor_offset(ev.pose,"chest",-1,ev.canvas_tilt)
		var ratio = clampf((fist.y-head.y)/(chest.y-head.y),0.0,1.0)
		print("CONTACT ",id," dx=",absf(fist.x-head.lerp(chest,ratio).x)," fist=",fist," chest=",chest)
		if id == "sweep":
			var layer = a.layer_3d
			var transforms = layer.drv.pose_global_transforms(pv.pose)
			var endpoint: Array = layer.motion.apose_points.f_foot
			var local_point = (layer.drv.global_rest.shin_f as Transform3D).affine_inverse()*Vector3(endpoint[0],endpoint[1],0.0)
			var point = (transforms.shin_f as Transform3D)*local_point
			var skeleton_in_model = layer.model_root.global_transform.affine_inverse()*layer.drv.skel.global_transform
			var pixel = layer.cam.unproject_position(layer.imported_model_transform*skeleton_in_model*point)
			var ground_pixel = layer.cam.unproject_position(Vector3(0.0,layer.NATIVE_GROUND_Y,0.0))
			var foot = a.player.position+pv.canvas_shift+Vector2((pixel.x-float(layer.SV_W)*0.5)*layer.DRAW_SCALE,(pixel.y-ground_pixel.y)*layer.DRAW_SCALE)
			print("SWEEP FOOT ",foot," defender base=",a.enemy.position+ev.canvas_shift," spark=",a.effects)
	var parts: Array = [{"name":"招式","op":"base","value":10},{"name":"三同","op":"+","value":4},{"name":"蓄势","op":"+","value":3},{"name":"追击","op":"+","value":3},{"name":"确反","op":"+","value":3},{"name":"EX牌型","op":"×","value":1.35},{"name":"三重奏","op":"+","value":2},{"name":"掠影","op":"+","value":3},{"name":"趁隙","op":"×","value":1.25},{"name":"格挡","op":"×","value":0.2}]
	var pieces: Array = []
	for part in parts:
		pieces.append(part.name+(str(int(part.value)) if part.op=="base" else part.op+("%.2f" % float(part.value) if part.op=="×" else str(int(part.value)))))
	print("FORMULA LINES ",a.hud._wrap_pixels(" → ".join(PackedStringArray(pieces)),236,12))
	a.free()
	print("REVIEW EDGE CHECK failures=",failures)
	quit(0 if failures.is_empty() else 1)
