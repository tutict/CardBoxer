extends SceneTree
const FighterScript = preload("res://scripts/fighter.gd")
const Presentation = preload("res://scripts/battle_presentation.gd")
const NativeMotion = preload("res://scripts/native_motion.gd")
const ArenaScript = preload("res://scripts/arena.gd")
var failures: Array[String] = []
var total := 0

func expect(ok: bool, label: String) -> void:
	total += 1
	if not ok: failures.append(label)

func _initialize() -> void:
	call_deferred("_run")

func quaternion(values: Array) -> Quaternion:
	return Quaternion(values[0],values[1],values[2],values[3])

func same_pose(a: Dictionary, b: Dictionary) -> bool:
	for bone: String in a.rotations:
		if absf(quaternion(a.rotations[bone]).dot(quaternion(b.rotations[bone]))) < 0.999999: return false
	for axis in range(3):
		if absf(float(a.root_offset[axis]) - float(b.root_offset[axis])) > 0.000001: return false
	return true

func half_pose(from: Dictionary, to: Dictionary) -> Dictionary:
	var out: Dictionary = to.duplicate(true)
	for bone: String in out.rotations:
		var q := quaternion(from.rotations[bone]).slerp(quaternion(to.rotations[bone]),0.5)
		out.rotations[bone] = [q.x,q.y,q.z,q.w]
	for axis in range(3): out.root_offset[axis] = (float(from.root_offset[axis]) + float(to.root_offset[axis])) * 0.5
	return out

func _run() -> void:
	var library = NativeMotion.new()
	expect(library.load_data(),"real authored native motion loads")
	if library.available():
		check_direction(library)
		check_blends(library)
	if OS.get_environment("CARD_BOXER_3D") != "": check_fx()
	for failure in failures: print("FAIL: ",failure)
	print("BATTLE TRANSITION CHECK: %d/%d passed" % [total-failures.size(),total])
	quit(0 if failures.is_empty() else 1)

func check_direction(library) -> void:
	for role: String in ["player","foe"]:
		for facing in [-1,1]:
			var forward = FighterScript.new()
			var backward = FighterScript.new()
			forward.is_player = role == "player"
			backward.is_player = role == "player"
			forward.reset_for_round(640,facing)
			backward.reset_for_round(640,facing)
			forward.tick(0.05,float(facing),true)
			backward.tick(0.05,float(-facing),true)
			var toward: Dictionary = forward.presentation_snapshot()
			var away: Dictionary = backward.presentation_snapshot()
			expect(int(toward.get("walk_direction",0)) == 1 and int(away.get("walk_direction",0)) == -1,"%s face%d retains signed travel relative to facing" % [role,facing])
			expect(is_equal_approx(forward.position.x,640.0+10.75*facing) and is_equal_approx(backward.position.x,640.0-10.75*facing),"%s face%d keeps exact gameplay displacement" % [role,facing])
			var controller = Presentation.new()
			controller.setup(library)
			controller.reset(1)
			var context := {"mode":"realtime"}
			var ahead: Dictionary = controller.sample(role,toward,context)
			controller.reset(1)
			var behind: Dictionary = controller.sample(role,away,context)
			var last: float = library.clip_frames(role,"walk")-1
			expect(is_equal_approx(ahead.frame/last,0.0895833333) and is_equal_approx(behind.frame/last,0.9104166667),"%s face%d reverses distance gait progression on retreat" % [role,facing])
			expect(not same_pose(ahead.pose,behind.pose),"%s face%d forward/backward legs differ" % [role,facing])
			forward.free()
			backward.free()

func check_blends(library) -> void:
	for role: String in ["player","foe"]:
		var controller = Presentation.new()
		controller.setup(library)
		var idle := {"state":0,"action_seq":0,"facing":1,"hp":100,"local_hitstop":0.0}
		var action := {"state":1,"card_id":"jab","action_seq":1,"phase":"windup","phase_progress":0.0,"facing":1,"hp":100,"local_hitstop":0.0}
		var context := {"mode":"realtime","pause":false,"global_hitstop":0.0,"snapshots":{role:action}}
		controller.reset(2)
		controller.advance(0.15,context)
		var outgoing: Dictionary = controller.sample(role,idle,context).pose
		var target: Dictionary = library.sample(role,"jab",0.0)
		expect(not same_pose(outgoing,target),role+" fixture idle breathing differs from guard")
		var start: Dictionary = controller.sample(role,action,context)
		expect(start.clip_id == "jab" and start.frame == 0.0,role+" transition retains native frame diagnostics")
		expect(same_pose(start.pose,outgoing),role+" ordinary action starts from last displayed idle")
		controller.advance(0.03,context)
		var middle: Dictionary = controller.sample(role,action,context).pose
		expect(same_pose(middle,half_pose(outgoing,target)),role+" ordinary transition reaches shortest-path half pose at .03s")
		var paused: Dictionary = context.duplicate(true)
		paused.pause = true
		controller.advance(0.2,paused)
		expect(same_pose(controller.sample(role,action,paused).pose,middle),role+" pause freezes transition time")
		var held: Dictionary = context.duplicate(true)
		held.global_hitstop = 0.2
		controller.advance(0.2,held)
		expect(same_pose(controller.sample(role,action,held).pose,middle),role+" global hitstop freezes transition time")
		held.global_hitstop = 0.0
		held.snapshots[role].local_hitstop = 0.2
		controller.advance(0.2,held)
		expect(same_pose(controller.sample(role,action,held).pose,middle),role+" local hitstop freezes transition time")
		controller.advance(0.03,context)
		expect(same_pose(controller.sample(role,action,context).pose,target),role+" ordinary transition finishes at .06s")
		controller.reset(3)
		expect(same_pose(controller.sample(role,action,context).pose,target),role+" reset removes outgoing blend pose")
		var walking: Dictionary = idle.duplicate()
		walking.walk_blend = 1.0
		walking.walk_phase = 0.25
		walking.walk_direction = 1
		controller.reset(4)
		var stride: Dictionary = controller.sample(role,walking,context).pose
		expect(same_pose(controller.sample(role,action,context).pose,stride),role+" walking stride blends into a new action")
		var struck := {"state":2,"action_seq":1,"facing":1,"hp":96,"stun_duration":0.26,"state_time":0.0,"local_hitstop":0.085}
		controller.record_impact({"round_id":4,"actor":"foe" if role == "player" else "player","target":role,"action_seq":1,"clip_id":"jab","source_kind":"melee","stun_duration":0.26})
		expect(same_pose(controller.sample(role,struck,context).pose,library.sample(role,"hit_light",0.0)),role+" reaction bypasses active blend immediately")
		controller.reset(5)
		controller.sample(role,walking,context)
		controller.sample(role,action,context)
		controller.begin_exchange({"round_id":5,"winner":role,"actor":role,"target":"foe" if role == "player" else "player","clip_id":"jab","action_seq":2})
		var taikou := {"mode":"taikou","pause":false,"global_hitstop":0.0}
		controller.advance(0.481,taikou)
		var contact: Dictionary = controller.sample(role,action,taikou)
		expect(contact.frame == 6.0 and same_pose(contact.pose,library.sample(role,"jab",6.0)),role+" contact bypasses active blend at exact native peak")
		controller.reset(6)
		var forward_stride: Dictionary = controller.sample(role,walking,context).pose
		var retreat: Dictionary = walking.duplicate()
		retreat.walk_direction = -1
		var backward_target: Dictionary = library.sample(role,"walk",0.75*float(library.clip_frames(role,"walk")-1))
		var reversal: Dictionary = controller.sample(role,retreat,context)
		expect(same_pose(reversal.pose,forward_stride),role+" direction reversal while walking starts from displayed stride")
		expect(is_equal_approx(reversal.frame,0.75*float(library.clip_frames(role,"walk")-1)),role+" reversal keeps reversed native gait diagnostics")
		controller.advance(0.03,context)
		expect(same_pose(controller.sample(role,retreat,context).pose,half_pose(forward_stride,backward_target)),role+" walking reversal reaches blend midpoint at .03s")
		controller.advance(0.03,context)
		expect(same_pose(controller.sample(role,retreat,context).pose,backward_target),role+" walking reversal completes at .06s")

func check_fx() -> void:
	var a = ArenaScript.new()
	root.add_child(a)
	a.set_process(false)
	a.battle_mode = "taikou"
	a._start_round()
	a.round_phase = "fight"
	a.tk_player_result = preload("res://scripts/taikou_rules.gd").evaluate([1,2,4])
	a.tk_enemy_result = preload("res://scripts/taikou_rules.gd").evaluate([1,1,2])
	a._resolve_taikou()
	a._advance_presentation(0.48)
	a._sync_3d_layer()
	var visual: Dictionary = a.last_visuals.foe
	var attack: Dictionary = a.last_visuals.player
	var fist: Vector2 = a.player.position+attack.canvas_shift+a.layer_3d.anchor_offset(attack.pose,"lead_hand",attack.facing,attack.canvas_tilt)
	var head: Vector2 = a.enemy.position+visual.canvas_shift+a.layer_3d_foe.anchor_offset(visual.pose,"head",visual.facing,visual.canvas_tilt)
	var chest: Vector2 = a.enemy.position+visual.canvas_shift+a.layer_3d_foe.anchor_offset(visual.pose,"chest",visual.facing,visual.canvas_tilt)
	var weight := clampf((fist.y-head.y)/(chest.y-head.y),0.0,1.0) if absf(chest.y-head.y)>0.0001 else 0.5
	var expected: Vector2 = head.lerp(chest,weight)
	var found := false
	for effect: Dictionary in a.effects:
		if effect.kind == "spark":
			found = true
			expect((effect.pos as Vector2).distance_to(expected) < 0.0001,"deferred native spark follows presented shift and tilt at contact")
			break
	expect(found,"real deferred contact emits a spark")
	a.queue_free()
