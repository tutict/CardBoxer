extends SceneTree
const Motion = preload("res://scripts/native_motion.gd")
const Flow = preload("res://scripts/battle_presentation.gd")
const Layer = preload("res://scripts/fighter_3d_layer.gd")
var failures: Array[String] = []
var total := 0

func expect(ok: bool, label: String) -> void:
	total += 1
	if not ok: failures.append(label)

func fixture() -> Dictionary:
	var keys := []
	for item: Array in [[0.0,.25,.75],[2.0,.5,.5],[6.0,.75,.25]]:
		var rotations := {}
		for bone: String in Motion.BONES: rotations[bone] = [0.0,0.0,0.0,1.0]
		keys.append({"frame":item[0],"rotations":rotations,"root_offset":[0.0,0.0,0.0],"hand_grip":[item[1],item[2]]})
	return {"roles":{"player":{"clips":{"hands":{"frames":7,"keys":keys}}}}}

func make_mesh() -> MeshInstance3D:
	var mesh := ArrayMesh.new()
	for name: String in ["grip_half_f","grip_f","grip_half_b","grip_b"]: mesh.add_blend_shape(name)
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO,Vector3.RIGHT,Vector3.UP])
	arrays[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3.FORWARD,Vector3.FORWARD,Vector3.FORWARD])
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0,1,2])
	var shapes: Array[Array] = []
	for index in range(4):
		var shape := []
		shape.resize(Mesh.ARRAY_MAX)
		shape[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO,Vector3.RIGHT,Vector3.UP+Vector3.FORWARD*float(index+1)*.1])
		shape[Mesh.ARRAY_NORMAL] = arrays[Mesh.ARRAY_NORMAL].duplicate()
		shapes.append(shape)
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays,shapes)
	var node := MeshInstance3D.new()
	node.mesh = mesh
	return node

func _initialize() -> void: call_deferred("run")

func run() -> void:
	var lib = Motion.new()
	lib.set("_data",fixture())
	var exact: Dictionary = lib.sample("player","hands",2.0)
	expect(exact.get("hand_grip",[]) == [.5,.5],"authored hand key preserved exactly")
	var middle: Dictionary = lib.sample("player","hands",3.5)
	var middle_grip: Array = middle.get("hand_grip",[])
	expect(middle_grip.size()==2,"hand-only interpolation is sampled")
	if middle_grip.size()==2:
		expect(middle_grip[0]>.5 and middle_grip[0]<.75,"front hand interpolates between nonuniform keys")
		expect(middle_grip[1]<.5 and middle_grip[1]>.25,"rear hand interpolates independently")
	var first: Dictionary = fixture().roles.player.clips.hands.keys[0]
	var last: Dictionary = fixture().roles.player.clips.hands.keys[-1]
	expect(not lib._same_pose(first,last),"different hands invalidate otherwise identical body pose")
	for frame in range(121):
		var pose: Dictionary = lib.sample("player","hands",frame/20.0)
		expect(pose.root_offset==[0.0,0.0,0.0] and pose.rotations.chest==[0.0,0.0,0.0,1.0],"hand sampling leaves body unchanged")
	var flow = Flow.new()
	var from_pose: Dictionary = first.duplicate(true)
	var to_pose: Dictionary = last.duplicate(true)
	var blended: Dictionary = flow._mix_pose(from_pose,to_pose,.5)
	expect(blended.get("hand_grip",[])==[.5,.5],"ordinary transitions blend both hand controls")
	var helper_type = load("res://scripts/hand_shape.gd") if FileAccess.file_exists("res://scripts/hand_shape.gd") else null
	expect(helper_type!=null,"progressive hand helper exists")
	if helper_type!=null:
		var helper = helper_type.new()
		expect(helper.valid_grip([.0,1.0]),"valid endpoints accepted")
		expect(not helper.valid_grip([NAN,.5]) and not helper.valid_grip([-.1,.5]) and not helper.valid_grip([.5,1.1]),"invalid hand values rejected")
		for item: Array in [[0.0,Vector3(1,0,0)],[.25,Vector3(.5,.5,0)],[.5,Vector3(0,1,0)],[.75,Vector3(0,.5,.5)],[1.0,Vector3(0,0,1)]]:
			expect(helper.weights(item[0]).is_equal_approx(item[1]),"progressive coefficients at "+str(item[0]))
		var profile := {"hand_sockets":{"front":{"open":[0,0,0],"half":[1,0,0],"closed":[1,1,0]},"rear":{"open":[0,0,1],"half":[0,1,1],"closed":[0,2,1]}}}
		expect(helper.valid_profile(profile),"both hand profiles are valid")
		expect(helper.socket(profile,true,.75).is_equal_approx(Vector3(1,.5,0)),"front contact follows the same half/full morph mixture")
		expect(helper.socket(profile,false,.25).is_equal_approx(Vector3(0,.5,1)),"rear contact follows the same open/half mixture")
	var layer = Layer.new()
	var mi := make_mesh()
	layer._collect_meshes(mi)
	expect(layer.has_method("apply_hand_grip"),"layer can apply hand-only changes")
	if layer.has_method("apply_hand_grip"):
		expect(layer.call("apply_hand_grip",[.25,.75]),"valid grip applied to real MeshInstance3D")
		expect(is_equal_approx(mi.get_blend_shape_value(0),.5) and is_equal_approx(mi.get_blend_shape_value(1),0.0),"front actual morph values match open-half")
		expect(is_equal_approx(mi.get_blend_shape_value(2),.5) and is_equal_approx(mi.get_blend_shape_value(3),.5),"rear actual morph values match half-closed")
		expect(not layer.call("apply_hand_grip",[NAN,.5]),"invalid shape update rejected")
		expect(is_equal_approx(mi.get_blend_shape_value(0),.5),"invalid update preserves previous hand")
		layer.call("apply_hand_grip",[.0,1.0])
		expect(is_equal_approx(mi.get_blend_shape_value(0),0.0) and is_equal_approx(mi.get_blend_shape_value(2),0.0) and is_equal_approx(mi.get_blend_shape_value(3),1.0),"subsequent hand-only update replaces all old coefficients")
	mi.free()
	layer.free()
	lib = Motion.new()
	expect(lib.load_data(),"production motion remains loadable")
	if lib.available():
		flow.setup(lib)
		flow.reset(1)
		flow.begin_exchange({"round_id":1,"actor":"player","winner":"player","target":"foe","clip_id":"wave","action_seq":1})
		var context := {"mode":"taikou","pause":false,"global_hitstop":0.0}
		var snapshot := {"state":0,"action_seq":1,"facing":1}
		flow.advance(.21,context)
		var before: Dictionary = flow.sample("player",snapshot,context).pose
		expect(before.get("hand_grip",[]).size()==2,"production hand timeline exists")
		var paused: Dictionary = context.duplicate(true)
		paused.pause = true
		flow.advance(.3,paused)
		expect(flow.sample("player",snapshot,paused).pose.get("hand_grip",[])==before.get("hand_grip",[]),"pause freezes displayed hands")
		var held: Dictionary = context.duplicate(true)
		held.global_hitstop = .1
		flow.advance(.3,held)
		expect(flow.sample("player",snapshot,held).pose.get("hand_grip",[])==before.get("hand_grip",[]),"global hitstop freezes displayed hands")
		flow.reset(2)
		var reset_pose: Dictionary = flow.sample("player",snapshot,context).pose
		expect(reset_pose.get("hand_grip",[])==[.75,.75],"round reset returns to guard hand state")
		var ko_pose: Dictionary = flow.sample("player",{"state":5,"state_time":.45,"facing":1},context).pose
		expect(ko_pose.get("hand_grip",[])==[0.0,0.0],"completed KO has relaxed hands")
	for failure: String in failures: print("FAIL: ",failure)
	print("HAND SHAPE CHECK: %d/%d passed" % [total-failures.size(),total])
	quit(0 if failures.is_empty() else 1)
