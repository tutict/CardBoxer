extends SceneTree
const Motion = preload("res://scripts/native_motion.gd")
const Flow = preload("res://scripts/battle_presentation.gd")
var failures: Array[String] = []
var total := 0

func expect(ok: bool, label: String) -> void:
	total += 1
	if not ok: failures.append(label)

func quat(values: Array) -> Quaternion:
	return Quaternion(values[0],values[1],values[2],values[3])

func rotation_step(a: Dictionary, b: Dictionary) -> float:
	var delta := quat(a.rotations.chest).inverse() * quat(b.rotations.chest)
	return 2.0 * atan2(Vector3(delta.x,delta.y,delta.z).length(),absf(delta.w))

func same_pose(a: Dictionary,b: Dictionary) -> bool:
	for bone: String in a.rotations:
		if absf(quat(a.rotations[bone]).dot(quat(b.rotations[bone]))) < .999999: return false
	return Vector3(a.root_offset[0],a.root_offset[1],a.root_offset[2]).distance_to(Vector3(b.root_offset[0],b.root_offset[1],b.root_offset[2])) < .000001

func fixture() -> Dictionary:
	var keys := []
	for item: Array in [[0.0,0.0],[2.0,.3],[5.0,.9],[9.0,1.5]]:
		var rotations := {}
		var q := Quaternion(Vector3.UP,float(item[1]))
		for bone: String in Motion.BONES: rotations[bone] = [q.x,q.y,q.z,q.w]
		keys.append({"frame":item[0],"rotations":rotations,"root_offset":[item[1],.1*item[1],0.0]})
	return {"roles":{"player":{"clips":{"curve":{"frames":10,"contact_frame":-1,"keys":keys}}}}}

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var lib = Motion.new()
	lib.set("_data",fixture())
	for frame in [2.0,5.0]:
		var before: Dictionary = lib.sample("player","curve",frame-.01)
		var center: Dictionary = lib.sample("player","curve",frame)
		var after: Dictionary = lib.sample("player","curve",frame+.01)
		var left := rotation_step(before,center)/.01
		var right := rotation_step(center,after)/.01
		expect((left+right)*.5 > .09,"non-contact intermediate quaternion keeps moving at frame"+str(frame))
		expect(absf(left-right) < .003,"nonuniform key times have continuous angular velocity at frame"+str(frame))
		var left_root := (float(center.root_offset[0])-float(before.root_offset[0]))/.01
		var right_root := (float(after.root_offset[0])-float(center.root_offset[0]))/.01
		expect((left_root+right_root)*.5 > .09 and absf(left_root-right_root)<.003,"root has continuous nonzero velocity at frame"+str(frame))
	for key: Dictionary in fixture().roles.player.clips.curve.keys:
		var pose: Dictionary = lib.sample("player","curve",key.frame)
		expect(pose.rotations == key.rotations and pose.root_offset == key.root_offset,"authored key remains exact "+str(key.frame))
	for frame in range(180):
		var pose: Dictionary = lib.sample("player","curve",frame/20.0)
		expect(absf(quat(pose.rotations.chest).length_squared()-1.0)<.000001,"interpolated rotation stays unit")
	expect(lib.load_data(),"production motion loads")
	if lib.available():
		for role: String in ["player","foe"]:
			check_flow(lib,role)
			check_support(lib,role)
	for failure: String in failures: print("FAIL: ",failure)
	print("NATURAL RUNTIME CHECK: %d/%d passed" % [total-failures.size(),total])
	quit(0 if failures.is_empty() else 1)

func check_flow(lib,role: String) -> void:
	var flow = Flow.new()
	flow.setup(lib)
	flow.reset(1)
	var context := {"mode":"taikou","pause":false,"global_hitstop":0.0}
	var snapshot := {"state":0,"action_seq":1,"facing":1 if role=="player" else -1}
	var distance := 280.0 if role=="player" else -280.0
	flow.begin_exchange({"round_id":1,"actor":role,"winner":role,"target":"foe" if role=="player" else "player","clip_id":"jab","action_seq":1,"approach_extra_x":distance})
	flow.advance(.20,context)
	var ahead: Dictionary = flow.sample(role,snapshot,context)
	var authored: Dictionary = lib.sample(role,"jab",ahead.frame)
	expect(ahead.pose.rotations.thigh_f != authored.rotations.thigh_f,role+" approach steps")
	var paused: Dictionary = context.duplicate(true)
	paused.pause = true
	flow.advance(.2,paused)
	expect(same_pose(flow.sample(role,snapshot,paused).pose,ahead.pose),role+" pause freezes approach footwork")
	flow.advance(.28,context)
	var contact: Dictionary = flow.sample(role,snapshot,context)
	expect(contact.frame==lib.contact_frame(role,"jab") and same_pose(contact.pose,lib.sample(role,"jab",contact.frame)),role+" exact calibrated contact untouched by stepping")
	expect(is_equal_approx(absf(contact.canvas_shift.x),382.1428571429),role+" exact calibrated contact shift retained")
	flow.advance(.20,context)
	expect(same_pose(flow.sample(role,snapshot,context).pose,contact.pose),role+" contact hold freezes pose")
	flow.advance(.04,context)
	flow.advance(.04,context)
	var retract: Dictionary = flow.sample(role,snapshot,context)
	expect(is_equal_approx(retract.canvas_shift.x,contact.canvas_shift.x),role+" hand retracts before torso retreat")
	flow.advance(.24,context)
	var retreat: Dictionary = flow.sample(role,snapshot,context)
	var recovery: Dictionary = lib.sample(role,"jab",retreat.frame)
	expect(retreat.pose.rotations.thigh_f != recovery.rotations.thigh_f,role+" return has backward stepping")
	if flow.has_method("_travel_legs"):
		var forward: Dictionary = flow._travel_legs(role,recovery,30.0,1.0)
		var backward: Dictionary = flow._travel_legs(role,recovery,-30.0,1.0)
		expect(forward.rotations.thigh_f != backward.rotations.thigh_f,role+" signed travel reverses gait")
	else: expect(false,role+" footwork follows signed visual travel")
	flow.advance(.36,context)
	var end: Dictionary = flow.sample(role,snapshot,context)
	expect(end.canvas_shift==Vector2.ZERO and same_pose(end.pose,lib.sample(role,"jab",lib.clip_frames(role,"jab")-1)),role+" recovery ends exactly at zero shift and guard")

func check_support(lib,role: String) -> void:
	if not lib.has_method("support_height"):
		expect(false,"real imported sole support measurement available")
		return
	var flow = Flow.new()
	flow.setup(lib)
	flow.reset(2)
	var context := {"mode":"taikou"}
	var snapshot := {"state":0,"action_seq":2,"facing":1 if role=="player" else -1}
	flow.begin_exchange({"round_id":2,"actor":role,"winner":role,"clip_id":"jab","action_seq":2,"approach_extra_x":280.0 if role=="player" else -280.0})
	var greatest := 0.0
	var full := full_boot_cache(role)
	var start := Time.get_ticks_usec()
	for step in range(41):
		flow.exchange_time = Flow.ATTACK_S*float(step)/40.0
		flow.sample(role,snapshot,context)
		flow._transitions.clear()
		var visual: Dictionary = flow.sample(role,snapshot,context)
		var authored: Dictionary = lib.sample(role,"jab",visual.frame)
		var sole := full_sole(full,visual.pose)
		greatest = maxf(greatest,absf(sole))
		expect(absf(sole-lib.support_height(role,authored))<.00001,role+" mixed gait retains actual skinned sole support")
		expect(absf(sole-lib.support_height(role,visual.pose))<.000001,role+" packed support equals independently posed full imported Skeleton/Skin")
		for bone: String in ["hips","spine","chest","upperarm_f","forearm_f","upperarm_b","forearm_b"]:
			expect(visual.pose.rotations[bone]==authored.rotations[bone],role+" gait retains authored upper-body rotation")
		expect(greatest<.02,role+" complete approach/return soles remain within2cm")
	print("TRAVEL SUPPORT ",role," max_m=",greatest," verify_ms=",(Time.get_ticks_usec()-start)/1000.0)
	full.model.free()

func find_rig(node: Node,skeleton: bool) -> Node:
	if (skeleton and node is Skeleton3D) or (not skeleton and node is MeshInstance3D and node.skin!=null): return node
	for child: Node in node.get_children():
		var found := find_rig(child,skeleton)
		if found!=null: return found
	return null

func full_boot_cache(role: String) -> Dictionary:
	var model: Node = load("res://assets/3d/"+role+"-rigged.glb").instantiate()
	root.add_child(model)
	var skeleton := find_rig(model,true) as Skeleton3D
	var mesh := find_rig(model,false) as MeshInstance3D
	var surface := mesh.mesh.surface_get_arrays(0)
	var vertices: PackedVector3Array = surface[Mesh.ARRAY_VERTEX]
	var joints: PackedInt32Array = surface[Mesh.ARRAY_BONES]
	var weights: PackedFloat32Array = surface[Mesh.ARRAY_WEIGHTS]
	var count := int(joints.size()/vertices.size())
	var boots := []
	for vertex in range(vertices.size()):
		if vertices[vertex].y >= .24: continue
		var influences := []
		var front := 0.0
		var rear := 0.0
		for index in range(count):
			var slot := joints[vertex*count+index]
			var weight := float(weights[vertex*count+index])
			if weight<=.000001: continue
			var name := String(mesh.skin.get_bind_name(slot))
			var bone := skeleton.find_bone(name) if not name.is_empty() else mesh.skin.get_bind_bone(slot)
			name = skeleton.get_bone_name(bone)
			if name=="shin_f": front += weight
			if name=="shin_b": rear += weight
			influences.append([bone,mesh.skin.get_bind_pose(slot)*vertices[vertex],weight])
		if front>.65 or rear>.65: boots.append(influences)
	expect(boots.size()>5000,role+" independent cache measures full imported boot mesh")
	return {"model":model,"skeleton":skeleton,"boots":boots}

func full_sole(cache: Dictionary,pose: Dictionary) -> float:
	var skeleton: Skeleton3D = cache.skeleton
	for bone: String in Motion.BONES:
		var index := skeleton.find_bone(bone)
		var rest := skeleton.get_bone_rest(index)
		var position := rest.origin
		if bone=="hips": position += Vector3(pose.root_offset[0],pose.root_offset[1],pose.root_offset[2])
		skeleton.set_bone_pose_position(index,position)
		skeleton.set_bone_pose_rotation(index,(rest.basis.get_rotation_quaternion()*quat(pose.rotations[bone])).normalized())
		skeleton.set_bone_pose_scale(index,rest.basis.get_scale())
	skeleton.force_update_all_bone_transforms()
	var matrices := {}
	for bone: String in Motion.BONES:
		var index := skeleton.find_bone(bone)
		matrices[index] = skeleton.get_bone_global_pose(index)
	var lowest := INF
	for vertex: Array in cache.boots:
		var height := 0.0
		for influence: Array in vertex: height += (matrices[influence[0]]*influence[1]).y*float(influence[2])
		lowest = minf(lowest,height)
	return lowest
