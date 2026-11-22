extends RefCounted
## Authored Skeleton3D local rest-relative poses. Coordinates: +Y up, +Z forward.
const Defs = preload("res://scripts/card_data.gd")
const Hands = preload("res://scripts/hand_shape.gd")
const BONES := ["hips", "spine", "chest", "neck", "head", "upperarm_f", "forearm_f", "upperarm_b", "forearm_b", "thigh_f", "shin_f", "thigh_b", "shin_b"]
var last_error := ""
var _data: Dictionary = {}
var _support_cache: Dictionary = {}

func _fail(message: String) -> bool:
	last_error = "NativeMotion: " + message
	_data.clear()
	return false

func _finite_array(value: Variant, count: int) -> bool:
	if not value is Array or value.size() != count:
		return false
	for number in value:
		if not (number is float or number is int) or not is_finite(float(number)):
			return false
	return true

func _quat(value: Array) -> Quaternion:
	return Quaternion(float(value[0]), float(value[1]), float(value[2]), float(value[3]))

func _same_pose(a: Dictionary, b: Dictionary) -> bool:
	var ag := Hands.grip(a)
	var bg := Hands.grip(b)
	if ag.size()!=2 or bg.size()!=2: return false
	for index in range(2):
		if absf(float(ag[index])-float(bg[index]))>.000001: return false
	for index in range(3):
		if absf(float(a.root_offset[index]) - float(b.root_offset[index])) > .000001:
			return false
	for bone in BONES:
		if absf(_quat(a.rotations[bone]).dot(_quat(b.rotations[bone]))) < .999999:
			return false
	return true

func load_data(path: String = "res://data/combat_motion_3d.json") -> bool:
	_data.clear()
	_support_cache.clear()
	last_error = ""
	if not FileAccess.file_exists(path):
		return _fail("file missing: " + path)
	var parser := JSON.new()
	if parser.parse(FileAccess.get_file_as_string(path)) != OK:
		return _fail("invalid JSON: " + parser.get_error_message())
	var parsed: Variant = parser.data
	if not parsed is Dictionary:
		return _fail("root must be a dictionary")
	if parsed.get("version") != 1 or parsed.get("coordinate_system") != "godot_y_up_z_forward":
		return _fail("unsupported version or coordinates")
	if parsed.get("bones", []) != BONES:
		return _fail("13 bone names/order must match native contract")
	var roles: Variant = parsed.get("roles", {})
	if not roles is Dictionary:
		return _fail("roles must be a dictionary")
	for role in ["player", "foe"]:
		if not roles.has(role) or not roles[role] is Dictionary:
			return _fail("missing role: " + role)
		var clips: Variant = roles[role].get("clips", {})
		if not clips is Dictionary:
			return _fail(role + ": clips must be a dictionary")
		for required in Array(Defs.CARDS.keys()) + ["stance", "idle", "walk", "ko", "hit_light", "hit_heavy", "block"]:
			if not clips.has(required):
				return _fail(role + ": missing clip " + required)
		for id in clips:
			var prefix: String = role + "/" + String(id)
			var clip: Variant = clips[id]
			if not clip is Dictionary:
				return _fail(prefix + ": clip must be a dictionary")
			var frame_value: Variant = clip.get("frames", 0)
			if not (frame_value is int or frame_value is float) or not is_finite(float(frame_value)) or float(frame_value) != floor(float(frame_value)) or int(frame_value) < 1:
				return _fail(prefix + ": frames must be a positive integer")
			var frames := int(frame_value)
			if (id == "stance" and frames != 1) or (id == "ko" and frames != 28):
				return _fail(prefix + ": required duration differs from native contract")
			var split: Variant = clip.get("split")
			if not _finite_array(split, 3):
				return _fail(prefix + ": invalid phase split")
			var total := 0
			for count in split:
				if float(count) < 0 or float(count) != floor(float(count)):
					return _fail(prefix + ": phase lengths must be nonnegative integers")
				total += int(count)
			if total != frames:
				return _fail(prefix + ": phase split does not sum to frames")
			var contact: Variant = clip.get("contact_frame")
			if not (contact is int or contact is float) or not is_finite(float(contact)) or float(contact) != floor(float(contact)):
				return _fail(prefix + ": invalid contact frame")
			if float(contact) < -1 or float(contact) >= frames:
				return _fail(prefix + ": contact frame out of range")
			if not Defs.CARDS.has(id) and int(contact) != -1:
				return _fail(prefix + ": only attack cards have a contact frame")
			if Defs.CARDS.has(id):
				var card: Dictionary = Defs.CARDS[id]
				var expected := [int(card.windup), int(card.active), int(card.recover)]
				if int(split[0]) != expected[0] or int(split[1]) != expected[1] or int(split[2]) != expected[2]:
					return _fail(prefix + ": split differs from gameplay card")
				var expected_contact := int(card.windup + card.active - 1) if card.kind == Defs.KIND_ATTACK else -1
				if int(contact) != expected_contact:
					return _fail(prefix + ": contact must be final active frame")
			var keys: Variant = clip.get("keys", [])
			if not keys is Array or keys.is_empty():
				return _fail(prefix + ": missing keys")
			var previous := -1.0
			for key in keys:
				if not key is Dictionary:
					return _fail(prefix + ": key must be a dictionary")
				var frame: Variant = key.get("frame", -1)
				if not (frame is float or frame is int) or not is_finite(float(frame)) or float(frame) <= previous or float(frame) >= frames:
					return _fail(prefix + ": keys must increase within frame range")
				previous = float(frame)
				if not _finite_array(key.get("root_offset"), 3):
					return _fail(prefix + ": invalid root offset")
				if key.has("hand_grip") and not Hands.valid_grip(key.hand_grip):
					return _fail(prefix + ": invalid hand grip")
				var rotations: Variant = key.get("rotations", {})
				if not rotations is Dictionary or rotations.size() != BONES.size():
					return _fail(prefix + ": key must contain exactly 13 rotations")
				for bone in BONES:
					if not _finite_array(rotations.get(bone), 4):
						return _fail(prefix + ": invalid quaternion for " + bone)
					if absf(_quat(rotations[bone]).length_squared() - 1.0) > 0.0001:
						return _fail(prefix + ": non-unit quaternion for " + bone)
			if float(keys[0].frame) != 0.0 or float(keys[-1].frame) != frames - 1.0:
				return _fail(prefix + ": keys must cover first and final frame")
			if int(contact) >= 0:
				var contact_authored := false
				for key in keys:
					if float(key.frame) == float(contact):
						contact_authored = true
				if not contact_authored:
					return _fail(prefix + ": final active contact must have an authored key")
		# Cross-clip validation runs after every quaternion/root has been validated.
		var stance_key: Dictionary = clips.stance["keys"][0]
		for id in clips:
			var keys: Array = clips[id]["keys"]
			if Defs.CARDS.has(id):
				if not _same_pose(keys[0], stance_key) or not _same_pose(keys[-1], stance_key):
					return _fail(role + "/" + String(id) + ": card endpoints must return to guard")
			if id in ["idle", "walk"] and not _same_pose(keys[0], keys[-1]):
				return _fail(role + "/" + String(id) + ": loop endpoints differ")
			if id in ["hit_light", "hit_heavy", "block"] and not _same_pose(keys[-1], stance_key):
				return _fail(role + "/" + String(id) + ": reaction must end at guard")
	_data = parsed
	return true

func available() -> bool:
	return not _data.is_empty()

func prepare_support() -> void:
	for role: String in ["player","foe"]: _boot_support(role)

func _clip(role: String, clip_id: String) -> Dictionary:
	if not available():
		last_error = "NativeMotion: library unavailable"
		return {}
	if not _data.roles.has(role) or not _data.roles[role].clips.has(clip_id):
		last_error = "NativeMotion: missing clip " + role + "/" + clip_id
		return {}
	return _data.roles[role].clips[clip_id]

func clip_frames(role: String, clip_id: String) -> int:
	var clip := _clip(role, clip_id)
	return int(clip.get("frames", 0))

func contact_frame(role: String, clip_id: String) -> float:
	var clip := _clip(role, clip_id)
	return float(clip.get("contact_frame", -1.0))

func phase_frame(role: String, clip_id: String, phase: String, progress: float) -> float:
	var clip := _clip(role, clip_id)
	if clip.is_empty():
		return -1.0
	if not is_finite(progress):
		last_error = "NativeMotion: phase progress must be finite"
		return -1.0
	var index := ["windup", "active", "recover"].find(phase)
	if index < 0:
		last_error = "NativeMotion: unknown phase " + phase
		return -1.0
	var start := 0
	for previous in range(index):
		start += int(clip.split[previous])
	var count := int(clip.split[index])
	if count == 0:
		return float(maxi(0, start - 1))
	return float(start) + float(count - 1) * clampf(progress, 0.0, 1.0)

func sample(role: String, clip_id: String, frame_float: float) -> Dictionary:
	var clip := _clip(role, clip_id)
	if clip.is_empty():
		return {"error": last_error, "clip_id": clip_id}
	if not is_finite(frame_float):
		last_error = "NativeMotion: sample frame must be finite"
		return {"error": last_error, "clip_id": clip_id}
	var frame := clampf(frame_float, 0.0, float(clip.frames - 1))
	var keys: Array = clip["keys"]
	var right_index := 0
	while right_index < keys.size()-1 and float(keys[right_index].frame) < frame:
		right_index += 1
	var right: Dictionary = keys[right_index]
	if frame == float(right.frame):
		return {"clip_id":clip_id,"frame":frame,"rotations":right.rotations.duplicate(true),"root_offset":right.root_offset.duplicate(),"hand_grip":Hands.grip(right)}
	var left_index := maxi(0,right_index-1)
	var left: Dictionary = keys[left_index]
	var span := float(right.frame) - float(left.frame)
	var t := (frame - float(left.frame)) / span if span > 0.0 else 0.0
	var previous: Dictionary = keys[maxi(0,left_index-1)]
	var following: Dictionary = keys[mini(keys.size()-1,right_index+1)]
	var pre_time := float(previous.frame)-float(left.frame)
	var post_time := float(following.frame)-float(left.frame)
	# Cyclic neighbours retain velocity across the walk/idle seam. Clamped card
	# neighbours keep the exact guard endpoints, without stopping at breakdowns.
	if clip_id in ["idle","walk"] and keys.size() > 2:
		var period := float(clip.frames-1)
		if left_index == 0:
			previous = keys[-2]
			pre_time = float(previous.frame)-period
		if right_index == keys.size()-1:
			following = keys[1]
			post_time = period+float(following.frame)-float(left.frame)
	var rotations := {}
	for bone in BONES:
		var a := _quat(left.rotations[bone])
		var b := _quat(right.rotations[bone])
		var pre := _quat(previous.rotations[bone])
		var post := _quat(following.rotations[bone])
		if a.dot(b) < 0.0: b = -b
		if a.dot(pre) < 0.0: pre = -pre
		if b.dot(post) < 0.0: post = -post
		var q := a.spherical_cubic_interpolate_in_time(b,pre,post,t,span,pre_time,post_time).normalized()
		rotations[bone] = [q.x, q.y, q.z, q.w]
	var a_root: Array = left.root_offset
	var b_root: Array = right.root_offset
	var root := []
	for axis in range(3):
		root.append(_monotone_component(float(previous.root_offset[axis]),float(a_root[axis]),float(b_root[axis]),float(following.root_offset[axis]),pre_time,span,post_time,t))
	var hand_grip := []
	var pre_grip := Hands.grip(previous)
	var a_grip := Hands.grip(left)
	var b_grip := Hands.grip(right)
	var post_grip := Hands.grip(following)
	for hand in range(2):
		hand_grip.append(clampf(_monotone_component(float(pre_grip[hand]),float(a_grip[hand]),float(b_grip[hand]),float(post_grip[hand]),pre_time,span,post_time,t),0.0,1.0))
	return {"clip_id": clip_id, "frame": frame, "rotations": rotations,
		"root_offset": root,"hand_grip":hand_grip}

## A shared time-aware slope at each key, bounded to avoid lifting planted soles
## through cubic root overshoot. Interior monotone keys retain nonzero velocity.
func _slope(before: float, after: float, before_span: float, after_span: float) -> float:
	if before_span <= 0.0 or after_span <= 0.0 or before*after <= 0.0: return 0.0
	var w1 := 2.0*after_span+before_span
	var w2 := after_span+2.0*before_span
	return (w1+w2)/(w1/before+w2/after)

func _monotone_component(pre: float,a: float,b: float,post: float,pre_time: float,span: float,post_time: float,t: float) -> float:
	var slope := (b-a)/span
	var before_span := -pre_time
	var after_span := post_time-span
	var before := (a-pre)/before_span if before_span>0.0 else 0.0
	var after := (post-b)/after_span if after_span>0.0 else 0.0
	var m0 := _slope(before,slope,before_span,span)*span
	var m1 := _slope(slope,after,span,after_span)*span
	var t2 := t*t
	var t3 := t2*t
	return (2.0*t3-3.0*t2+1.0)*a+(t3-2.0*t2+t)*m0+(-2.0*t3+3.0*t2)*b+(t3-t2)*m1

func _find_rig(node: Node, skeleton: bool) -> Node:
	if (skeleton and node is Skeleton3D) or (not skeleton and node is MeshInstance3D and node.skin != null): return node
	for child: Node in node.get_children():
		var found := _find_rig(child,skeleton)
		if found != null: return found
	return null

## Cache read-only imported bind data once. Footwork overlays use real weighted
## boot vertices, since a shin endpoint is not the visible sole of either model.
func _boot_support(role: String) -> Dictionary:
	if _support_cache.has(role): return _support_cache[role]
	var resource := load("res://assets/3d/"+role+"-rigged.glb") as PackedScene
	if resource == null: return {}
	var model := resource.instantiate()
	var skeleton := _find_rig(model,true) as Skeleton3D
	var instance := _find_rig(model,false) as MeshInstance3D
	if skeleton == null or instance == null:
		model.free()
		return {}
	var rests := {}
	var parents := {}
	for bone: String in BONES:
		var index := skeleton.find_bone(bone)
		rests[bone] = skeleton.get_bone_rest(index)
		var parent := skeleton.get_bone_parent(index)
		parents[bone] = skeleton.get_bone_name(parent) if parent >= 0 else ""
	var surface := instance.mesh.surface_get_arrays(0)
	var vertices: PackedVector3Array = surface[Mesh.ARRAY_VERTEX]
	var joints: PackedInt32Array = surface[Mesh.ARRAY_BONES]
	var weights: PackedFloat32Array = surface[Mesh.ARRAY_WEIGHTS]
	var count := int(joints.size()/vertices.size())
	var groups := {}
	for vertex in range(vertices.size()):
		if vertices[vertex].y >= .24: continue
		var influences := []
		var signature := ""
		var shin_weight := 0.0
		for influence in range(count):
			var slot := int(joints[vertex*count+influence])
			var weight := float(weights[vertex*count+influence])
			if weight <= .000001: continue
			var name := String(instance.skin.get_bind_name(slot))
			if name.is_empty(): name = skeleton.get_bone_name(instance.skin.get_bind_bone(slot))
			if name in ["shin_f","shin_b"]: shin_weight += weight
			signature += str(slot)+":"+String.num(weight,9)+";"
			influences.append([name,instance.skin.get_bind_pose(slot),weight])
		if shin_weight <= .65: continue
		if not groups.has(signature): groups[signature] = {"influences":influences,"points":PackedVector3Array()}
		groups[signature].points.append(vertices[vertex])
	model.free()
	_support_cache[role] = {"rests":rests,"parents":parents,"groups":groups.values()}
	return _support_cache[role]

func support_height(role: String,pose: Dictionary) -> float:
	var cache := _boot_support(role)
	if cache.is_empty(): return 0.0
	var transforms := {}
	# Native BONES follows parent order for both imported rigs.
	for bone: String in BONES:
		var rest: Transform3D = cache.rests[bone]
		var local := Transform3D(Basis(rest.basis.get_rotation_quaternion()*_quat(pose.rotations[bone])).scaled(rest.basis.get_scale()),rest.origin)
		var global_pose: Transform3D = transforms.get(cache.parents[bone],Transform3D.IDENTITY)*local
		if bone == "hips": global_pose.origin += Vector3(pose.root_offset[0],pose.root_offset[1],pose.root_offset[2])
		transforms[bone] = global_pose
	var lowest := INF
	for group: Dictionary in cache.groups:
		var axis_x := Vector3.ZERO
		var axis_y := Vector3.ZERO
		var axis_z := Vector3.ZERO
		var origin := Vector3.ZERO
		for influence: Array in group.influences:
			if not transforms.has(influence[0]): continue
			var matrix: Transform3D = transforms[influence[0]]*influence[1]
			var weight := float(influence[2])
			axis_x += matrix.basis.x*weight
			axis_y += matrix.basis.y*weight
			axis_z += matrix.basis.z*weight
			origin += matrix.origin*weight
		# Native packed-array multiplication evaluates exactly the same weighted
		# affine transform for every vertex in a skin-weight group. No proxy or
		# dropped boot vertex is used; the hot loop avoids Variant influences.
		var points: PackedVector3Array = Transform3D(Basis(axis_x,axis_y,axis_z),origin)*group.points
		for point: Vector3 in points: lowest = minf(lowest,point.y)
	return lowest if is_finite(lowest) else 0.0

func preserve_support(role: String,pose: Dictionary,reference: Dictionary) -> Dictionary:
	var out := pose.duplicate(true)
	out.root_offset[1] = float(out.root_offset[1])+support_height(role,reference)-support_height(role,pose)
	return out
