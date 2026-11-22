extends SceneTree
## Catches absent native data, transverse punches and phase/contact drift.
const Defs = preload("res://scripts/card_data.gd")
var failures := 0
var sampled_poses := 0
var max_support_error := 0.0
const BONES := ["hips", "spine", "chest", "neck", "head", "upperarm_f", "forearm_f", "upperarm_b", "forearm_b", "thigh_f", "shin_f", "thigh_b", "shin_b"]
const AUX := ["stance", "idle", "walk", "ko", "hit_light", "hit_heavy", "block"]

func check(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		print("FAIL: " + message)

func _init() -> void:
	if not FileAccess.file_exists("res://scripts/native_motion.gd"):
		check(false, "NativeMotion sampler missing: cannot render native guard/jab/cross/sweep")
		quit(1)
		return
	var script = load("res://scripts/native_motion.gd")
	if script == null:
		check(false, "NativeMotion script failed to load")
		quit(1)
		return
	var lib = script.new()
	check(lib.load_data(), "Native library must load: " + lib.last_error)
	if not lib.available():
		print(lib.last_error)
	if not lib.available():
		quit(1)
		return
	for role in ["player", "foe"]:
		for id in Array(Defs.CARDS.keys()) + AUX:
			check(lib.clip_frames(role, id) > 0, role + "/" + id + " full required coverage")
		for id in ["stance", "jab", "cross", "sweep"]:
			var pose: Dictionary = lib.sample(role, id, 0.0)
			check(pose.get("rotations", {}).size() == 13, role + "/" + id + " must drive all 13 bones")
		for id in ["jab", "cross", "sweep"]:
			var card: Dictionary = Defs.CARDS[id]
			var contact := float(card.windup + card.active - 1)
			check(is_equal_approx(lib.contact_frame(role, id), contact), role + "/" + id + " contact is final active frame")
			check(is_equal_approx(lib.phase_frame(role, id, "active", 1.0), contact), "active endpoint must not wrap")
			var first: Dictionary = lib.sample(role, id, 0.0)
			var last: Dictionary = lib.sample(role, id, lib.clip_frames(role, id) - 1.0)
			check(first.rotations == last.rotations and first.root_offset == last.root_offset, id + " returns exactly to guard")
		_geometry(lib, role)
		_all_endpoints(lib, role)
	_sampling_contract(script, lib)
	_invalid_data(script)
	print("NATIVE MOTION CHECK: " + ("PASS" if failures == 0 else "FAIL") + " failures=" + str(failures) + " sampled=" + str(sampled_poses) + " support_max_m=" + str(max_support_error))
	quit(0 if failures == 0 else 1)

func _find_skeleton(node: Node) -> Skeleton3D:
	if node is Skeleton3D:
		return node
	for child in node.get_children():
		var result := _find_skeleton(child)
		if result != null:
			return result
	return null

func _endpoint_pose(skel: Skeleton3D, source: Dictionary, pose: Dictionary) -> Dictionary:
	var transforms := {}
	var pending := BONES.duplicate()
	while not pending.is_empty():
		for bone in pending.duplicate():
			var index := skel.find_bone(bone)
			var parent_index := skel.get_bone_parent(index)
			var parent_name := skel.get_bone_name(parent_index) if parent_index >= 0 else ""
			if not parent_name.is_empty() and not transforms.has(parent_name):
				continue
			var rest := skel.get_bone_rest(index)
			var values: Array = pose.rotations[bone]
			var delta := Quaternion(values[0], values[1], values[2], values[3])
			var local := Transform3D(Basis(rest.basis.get_rotation_quaternion() * delta).scaled(rest.basis.get_scale()), rest.origin)
			var global_pose: Transform3D = transforms.get(parent_name, Transform3D.IDENTITY) * local
			if bone == "hips":
				var offset: Array = pose.root_offset
				global_pose.origin += Vector3(offset[0], offset[1], offset[2])
			transforms[bone] = global_pose
			pending.erase(bone)
	var endpoints := {"hip": transforms.hips.origin, "head": transforms.head.origin, "shoulder": transforms.upperarm_f.origin,
		"f_elbow": transforms.forearm_f.origin, "b_elbow": transforms.forearm_b.origin, "transforms": transforms}
	for pair in [["forearm_f", "f_hand"], ["forearm_b", "b_hand"], ["shin_f", "f_foot"], ["shin_b", "b_foot"]]:
		var rest_global := skel.get_bone_global_rest(skel.find_bone(pair[0]))
		var point: Array = source.apose_points[pair[1]]
		var tail := rest_global.affine_inverse() * Vector3(point[0], point[1], 0.0)
		endpoints[pair[1]] = transforms[pair[0]] * tail
	return endpoints

func _find_mesh(node: Node) -> MeshInstance3D:
	if node is MeshInstance3D and node.skin != null:
		return node
	for child in node.get_children():
		var result := _find_mesh(child)
		if result != null:
			return result
	return null

func _boot_cache(model: Node, skel: Skeleton3D) -> Dictionary:
	var instance := _find_mesh(model)
	check(instance != null, "actual imported skinned mesh available")
	var result := {"f": [], "b": []}
	if instance == null:
		return result
	var surface := instance.mesh.surface_get_arrays(0)
	var vertices: PackedVector3Array = surface[Mesh.ARRAY_VERTEX]
	var joints: PackedInt32Array = surface[Mesh.ARRAY_BONES]
	var weights: PackedFloat32Array = surface[Mesh.ARRAY_WEIGHTS]
	var count := joints.size() / vertices.size()
	for vertex in range(vertices.size()):
		if vertices[vertex].y >= .24:
			continue
		var influences: Array = []
		var shin_f_weight := 0.0
		var shin_b_weight := 0.0
		for influence in range(count):
			var slot := int(joints[vertex * count + influence])
			var weight := weights[vertex * count + influence]
			if weight <= .000001:
				continue
			var name := String(instance.skin.get_bind_name(slot))
			if name.is_empty():
				name = skel.get_bone_name(instance.skin.get_bind_bone(slot))
			if name == "shin_f": shin_f_weight += weight
			if name == "shin_b": shin_b_weight += weight
			influences.append([name, instance.skin.get_bind_pose(slot) * vertices[vertex], weight])
		if shin_f_weight > .65: result.f.append(influences)
		if shin_b_weight > .65: result.b.append(influences)
	check(result.f.size() > 50 and result.b.size() > 50, "actual boot vertices classified on both shins")
	print("IMPORTED BOOT VERTICES " + str(result.f.size()) + "/" + str(result.b.size()))
	return result

func _sole(cache: Dictionary, transforms: Dictionary, suffix: String) -> float:
	var lowest := INF
	for vertex in cache[suffix]:
		var height := 0.0
		for influence in vertex:
			if not transforms.has(influence[0]):
				continue
			var matrix: Transform3D = transforms[influence[0]]
			var rest_point: Vector3 = influence[1]
			height += (matrix * rest_point).y * float(influence[2])
		lowest = minf(lowest, height)
	return lowest

func _geometry(lib: RefCounted, role: String) -> void:
	var model: Node = load("res://assets/3d/" + role + "-rigged.glb").instantiate()
	var skel := _find_skeleton(model)
	check(skel != null, "actual imported Skeleton3D available for " + role)
	if skel == null:
		model.free()
		return
	var path := "res://data/motion_input.json" if role == "player" else "res://data/motion_input_foe.json"
	var source: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	var boot_cache := _boot_cache(model, skel)
	var guard := _endpoint_pose(skel, source, lib.sample(role, "stance", 0.0))
	check(guard.f_hand.z - guard.shoulder.z > .2 and guard.b_hand.z - guard.shoulder.z > .2, role + " both guard hands in +Z")
	check(guard.f_hand.z - guard.shoulder.z > .45 and guard.b_hand.z - guard.shoulder.z > .40, role + " guard hands clear chest occlusion")
	check(guard.f_hand.y - guard.shoulder.y > .16 and guard.b_hand.y - guard.shoulder.y > .17, role + " guard hands raised toward chin")
	check(guard.f_elbow.x > .16 and guard.b_elbow.x < -.16, role + " guard elbows stay independently separated")
	var jab := _endpoint_pose(skel, source, lib.sample(role, "jab", lib.contact_frame(role, "jab")))
	check(jab.f_hand.z > (.77 if role == "player" else .89) and jab.f_hand.z - guard.f_hand.z > .18, role + " jab retains full reach beyond refined guard")
	var cross_pose := _endpoint_pose(skel, source, lib.sample(role, "cross", lib.contact_frame(role, "cross")))
	check(cross_pose.b_hand.z > (.77 if role == "player" else .90) and cross_pose.b_hand.z - guard.b_hand.z > .25, role + " cross retains full independent rear reach")
	var sweep := _endpoint_pose(skel, source, lib.sample(role, "sweep", lib.contact_frame(role, "sweep")))
	check(sweep.f_foot.z > .55 and sweep.f_foot.y < .25, role + " sweep goes forward and stays low")
	check(absf(_sole(boot_cache, sweep.transforms, "b")) < .001, role + " actual sweep supporting boot sole grounded")
	check(absf(_sole(boot_cache, guard.transforms, "f")) < .001 and absf(_sole(boot_cache, guard.transforms, "b")) < .001, role + " actual guard boot soles grounded")
	for id in ["uppercut", "wave", "throw", "hit_light", "hit_heavy", "block", "ko", "idle", "walk"]:
		if lib.clip_frames(role, id) == 0:
			continue
		var frame: float = lib.contact_frame(role, id) if lib.contact_frame(role, id) >= 0 else 0.0
		var peak := _endpoint_pose(skel, source, lib.sample(role, id, frame))
		if id == "uppercut":
			check(peak.f_hand.y - guard.f_hand.y > .25, role + " uppercut has distinct upward strike")
		if id == "wave":
			check(peak.f_hand.z > guard.f_hand.z + .2 and peak.b_hand.z > guard.b_hand.z + .2, role + " wave extends both palms")
		if id == "ko":
			var down := _endpoint_pose(skel, source, lib.sample(role, id, 27.0))
			check(down.head.y < .55 and down.hip.y < .5, role + " KO ends down")
	for id in Array(Defs.CARDS.keys()) + AUX:
		for half_frame in range(lib.clip_frames(role, id) * 2 - 1):
			var sampled: Dictionary = lib.sample(role, id, half_frame * .5)
			sampled_poses += 1
			check(sampled.rotations.size() == 13, role + "/" + id + " sampled bone coverage")
			for bone in BONES:
				var values: Array = sampled.rotations[bone]
				var q := Quaternion(values[0], values[1], values[2], values[3])
				check(q.is_finite() and absf(q.length_squared() - 1.0) < .00001, role + "/" + id + " finite unit sample")
			if id in ["stance", "jab", "cross", "uppercut", "wave", "throw", "sweep", "guard", "sidestep", "focus", "recover", "idle", "walk", "hit_light", "hit_heavy", "block", "ko"]:
				var sampled_endpoints := _endpoint_pose(skel, source, sampled)
				var support_sides: Array = ["b"] if id in ["sweep", "ko"] else ["f", "b"]
				if id == "walk":
					support_sides = ["b"] if half_frame * .5 <= 17.0 else ["f"]
				for suffix in support_sides:
					var support_error := absf(_sole(boot_cache, sampled_endpoints.transforms, suffix))
					max_support_error = maxf(max_support_error, support_error)
					check(support_error < .025, role + "/" + id + " actual " + suffix + " boot support stays near floor at " + str(half_frame * .5))
	print("GEOMETRY " + role + " guard_z=" + str(guard.f_hand.z) + "/" + str(guard.b_hand.z) + " jab_z=" + str(jab.f_hand.z) + " cross_z=" + str(cross_pose.b_hand.z) + " sweep_z=" + str(sweep.f_foot.z))
	print("GUARD " + role + " hand_above_shoulder=" + str(guard.f_hand.y - guard.shoulder.y) + "/" + str(guard.b_hand.y - guard.shoulder.y) + " elbow_x=" + str(guard.f_elbow.x) + "/" + str(guard.b_elbow.x))
	model.free()

func _all_endpoints(lib: RefCounted, role: String) -> void:
	var stance: Dictionary = lib.sample(role, "stance", 0.0)
	check(lib.clip_frames(role, "stance") == 1 and lib.clip_frames(role, "ko") == 28, role + " required stance and KO durations")
	for id in Array(Defs.CARDS.keys()) + ["hit_light", "hit_heavy", "block", "idle", "walk"]:
		var first: Dictionary = lib.sample(role, id, 0.0)
		var last: Dictionary = lib.sample(role, id, lib.clip_frames(role, id) - 1.0)
		check(last.rotations == stance.rotations and last.root_offset == stance.root_offset, role + "/" + id + " closes on guard")
		if Defs.CARDS.has(id) or id in ["idle", "walk"]:
			check(first.rotations == last.rotations and first.root_offset == last.root_offset, role + "/" + id + " starts/ends at guard")
		else:
			check(first.rotations != stance.rotations, role + "/" + id + " reaction starts at impact")
	for id in Defs.CARDS:
		var card: Dictionary = Defs.CARDS[id]
		check(lib.clip_frames(role, id) == card.windup + card.active + card.recover, id + " native timing follows gameplay")
		check(is_equal_approx(lib.phase_frame(role, id, "windup", 1.0), float(card.windup - 1)), id + " windup endpoint")
		check(is_equal_approx(lib.phase_frame(role, id, "recover", 1.0), float(lib.clip_frames(role, id) - 1)), id + " recovery endpoint")
		if card.active == 0:
			check(is_equal_approx(lib.phase_frame(role, id, "active", 1.0), float(card.windup - 1)), id + " absent active phase does not enter recovery")
		check(lib.contact_frame(role, id) == -1.0 if card.kind != Defs.KIND_ATTACK else lib.contact_frame(role, id) == float(card.windup + card.active - 1), id + " attack-only contact")

func _write_fixture(data: Dictionary) -> String:
	var path := "res://tests/native-motion-invalid-fixture.json"
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(data))
	file.close()
	return path

func _sampling_contract(script: Script, lib: RefCounted) -> void:
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/combat_motion_3d.json"))
	var key0: Dictionary = data.roles.player.clips.stance["keys"][0].duplicate(true)
	var key2: Dictionary = key0.duplicate(true)
	key0.frame = 0
	key0.rotations.hips = [0.0, 0.0, 0.0, 1.0]
	key0.root_offset = [0.0, 0.0, 0.0]
	key2.frame = 2
	# Negative quaternion hemisphere deliberately exercises short-path interpolation.
	key2.rotations.hips = [0.0, -0.707106781186548, 0.0, -0.707106781186548]
	key2.root_offset = [.2, .1, -.3]
	data.roles.player.clips.interpolation_probe = {"frames":3, "split":[0,0,3], "contact_frame":-1, "keys":[key0,key2]}
	var probe = script.new()
	check(probe.load_data(_write_fixture(data)), "hand-derived interpolation fixture loads")
	var mid: Dictionary = probe.sample("player", "interpolation_probe", 1.0)
	var values: Array = mid.rotations.hips
	var q := Quaternion(values[0], values[1], values[2], values[3])
	check((q * Vector3.RIGHT).distance_to(Vector3(.707106781186548, 0.0, -.707106781186548)) < .00001, "fractional midpoint uses short-path 45 degree yaw")
	check(absf(mid.root_offset[0] - .1) < .00001 and absf(mid.root_offset[1] - .05) < .00001 and absf(mid.root_offset[2] + .15) < .00001, "fractional root midpoint interpolates once")
	var quarter: Dictionary = probe.sample("player", "interpolation_probe", .5)
	values = quarter.rotations.hips
	q = Quaternion(values[0], values[1], values[2], values[3])
	check(absf(q.dot(Quaternion(Vector3.UP, deg_to_rad(14.0625)))) > .99999, "sparse interval has smooth eased fractional rotation")
	check(probe.sample("player", "interpolation_probe", -3.0).frame == 0.0 and probe.sample("player", "interpolation_probe", 8.0).frame == 2.0, "sample clamps both clip endpoints")
	check(lib.sample("player", "missing", 0.0).has("error") and not lib.sample("missing", "jab", 0.0).has("rotations"), "missing native clip gives explicit diagnostic")
	check(lib.sample("player", "jab", NAN).has("error"), "nonfinite frame rejected")
	var original: Dictionary = lib.sample("player", "stance", 0.0)
	original.rotations.hips[0] = 123.0
	check(lib.sample("player", "stance", 0.0).rotations.hips[0] != 123.0, "sample output cannot mutate library")
	DirAccess.remove_absolute(ProjectSettings.globalize_path("res://tests/native-motion-invalid-fixture.json"))

func _reject(script: Script, data: Dictionary, label: String) -> void:
	var probe = script.new()
	var result: bool = probe.load_data(_write_fixture(data))
	check(not result and not probe.available() and not probe.last_error.is_empty(), "reject invalid " + label + " with diagnostic")

func _invalid_data(script: Script) -> void:
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/combat_motion_3d.json"))
	var broken := data.duplicate(true)
	broken.roles.foe.clips.erase("focus")
	_reject(script, broken, "missing full-set clip")
	broken = data.duplicate(true)
	broken.roles.player.clips.stance.frames = 2
	broken.roles.player.clips.stance.split = [0,0,2]
	broken.roles.player.clips.stance["keys"].append(broken.roles.player.clips.stance["keys"][0].duplicate(true))
	broken.roles.player.clips.stance["keys"][-1].frame = 1
	_reject(script, broken, "stance duration")
	broken = data.duplicate(true)
	broken.roles.player.clips.jab["keys"][0].rotations.hips = [0.,0.,0.,2.]
	_reject(script, broken, "non-unit quaternion")
	broken = data.duplicate(true)
	broken.roles.player.clips.jab["keys"][0].rotations.erase("head")
	_reject(script, broken, "missing bone quaternion")
	broken = data.duplicate(true)
	broken.roles.player.clips.jab["keys"][1].frame = 0
	_reject(script, broken, "nonincreasing keys")
	broken = data.duplicate(true)
	broken.roles.player.clips.jab["keys"][0].root_offset = [0.,0.]
	_reject(script, broken, "root dimensionality")
	broken = data.duplicate(true)
	broken.roles.player.clips.jab.contact_frame = 5
	_reject(script, broken, "contact drift")
	broken = data.duplicate(true)
	broken.roles.player.clips.jab["keys"][-1].root_offset[0] += .1
	_reject(script, broken, "open card endpoint")
	broken = data.duplicate(true)
	broken.roles.foe.clips.walk["keys"][-1].root_offset[0] += .1
	_reject(script, broken, "open looping walk endpoint")
	broken = data.duplicate(true)
	broken.roles.foe.clips.jab["keys"].remove_at(2)
	_reject(script, broken, "missing authored contact key")
	DirAccess.remove_absolute(ProjectSettings.globalize_path("res://tests/native-motion-invalid-fixture.json"))
