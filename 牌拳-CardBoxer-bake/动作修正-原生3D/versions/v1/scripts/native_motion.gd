extends RefCounted
## Authored Skeleton3D local rest-relative poses. Coordinates: +Y up, +Z forward.
const Defs = preload("res://scripts/card_data.gd")
const BONES := ["hips", "spine", "chest", "neck", "head", "upperarm_f", "forearm_f", "upperarm_b", "forearm_b", "thigh_f", "shin_f", "thigh_b", "shin_b"]
var last_error := ""
var _data: Dictionary = {}

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
	for index in range(3):
		if absf(float(a.root_offset[index]) - float(b.root_offset[index])) > .000001:
			return false
	for bone in BONES:
		if absf(_quat(a.rotations[bone]).dot(_quat(b.rotations[bone]))) < .999999:
			return false
	return true

func load_data(path: String = "res://data/combat_motion_3d.json") -> bool:
	_data.clear()
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
	var left: Dictionary = keys[0]
	var right: Dictionary = left
	for key in keys:
		right = key
		if float(key.frame) >= frame:
			break
		left = key
	var span := float(right.frame) - float(left.frame)
	var t := (frame - float(left.frame)) / span if span > 0.0 else 0.0
	# Zero endpoint velocity gives continuous interpolation between sparse beats.
	t = t * t * (3.0 - 2.0 * t)
	var rotations := {}
	for bone in BONES:
		if t <= 0.0:
			rotations[bone] = left.rotations[bone].duplicate()
		elif t >= 1.0:
			rotations[bone] = right.rotations[bone].duplicate()
		else:
			var a := _quat(left.rotations[bone])
			var b := _quat(right.rotations[bone])
			if a.dot(b) < 0.0:
				b = -b
			var q := a.slerp(b, t).normalized()
			rotations[bone] = [q.x, q.y, q.z, q.w]
	var a_root: Array = left.root_offset
	var b_root: Array = right.root_offset
	return {"clip_id": clip_id, "frame": frame, "rotations": rotations,
		"root_offset": [lerpf(a_root[0], b_root[0], t), lerpf(a_root[1], b_root[1], t), lerpf(a_root[2], b_root[2], t)]}
