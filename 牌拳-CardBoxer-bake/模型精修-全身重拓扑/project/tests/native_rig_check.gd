extends SceneTree
## Native deltas must use each imported bone's local rest exactly once.
const RigScript = preload("res://scripts/rig_driver.gd")
const LayerScript = preload("res://scripts/fighter_3d_layer.gd")
var failures: Array[String] = []
var checks := 0

func _initialize() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)

func _find_skel(node: Node) -> Skeleton3D:
	if node is Skeleton3D:
		return node as Skeleton3D
	for child in node.get_children():
		var found := _find_skel(child)
		if found != null:
			return found
	return null

func _pose(bones: Array) -> Dictionary:
	var rotations := {}
	for bone in bones:
		rotations[String(bone)] = [0.0, 0.0, 0.0, 1.0]
	return {"clip_id": "fixture", "frame": 0.5,
		"rotations": rotations, "root_offset": [0.0, 0.0, 0.0]}

func _check_role(role: String, glb: String, input: String) -> void:
	var packed: PackedScene = load(glb)
	_expect(packed != null, role + " GLB must load")
	if packed == null:
		return
	var model := packed.instantiate()
	root.add_child(model)
	var skel := _find_skel(model)
	_expect(skel != null, role + " must have a skeleton")
	if skel == null:
		model.free()
		return
	var motion: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(input))
	var driver: RefCounted = RigScript.new()
	_expect(driver.call("setup", skel, motion), role + " rig setup")
	_expect(driver.has_method("apply_pose"), role + " lacks native pose application")
	if not driver.has_method("apply_pose"):
		model.free()
		return
	var bones: Array = motion["bones"]
	var neutral := skel.find_bone("neutral_bone")
	var neutral_position := skel.get_bone_pose_position(neutral)
	var neutral_rotation := skel.get_bone_pose_rotation(neutral)
	var neutral_scale := skel.get_bone_pose_scale(neutral)
	var pose := _pose(bones)
	var result: Dictionary = driver.call("apply_pose", pose)
	_expect(int(result.get("bones_driven", 0)) == 13, role + " applies all 13 bones")
	for name in bones:
		var idx := skel.find_bone(String(name))
		var rest := skel.get_bone_rest(idx)
		_expect(skel.get_bone_pose_position(idx).is_equal_approx(rest.origin),
			role + " rest translation " + String(name))
		_expect(absf(skel.get_bone_pose_rotation(idx).dot(
			rest.basis.get_rotation_quaternion())) > 0.99999,
			role + " rest rotation " + String(name))
		_expect(skel.get_bone_pose_scale(idx).is_equal_approx(rest.basis.get_scale()),
			role + " rest scale " + String(name))

	# Local X on this measured bone is not a fixed skeleton/global Z axis.
	var delta := Quaternion(Vector3.RIGHT, 0.25)
	pose["rotations"]["upperarm_f"] = [delta.x, delta.y, delta.z, delta.w]
	pose["root_offset"] = [0.125, -0.05, 0.2]
	var arm_idx := skel.find_bone("upperarm_f")
	var hips_idx := skel.find_bone("hips")
	var arm_rest := skel.get_bone_rest(arm_idx)
	var hips_rest := skel.get_bone_rest(hips_idx)
	var want_rotation := arm_rest.basis.get_rotation_quaternion() * delta
	for _iteration in range(50):
		driver.call("apply_pose", pose)
	_expect(absf(skel.get_bone_pose_rotation(arm_idx).dot(want_rotation)) > 0.99999,
		role + " rotations cannot accumulate or use the wrong multiplication order")
	_expect(skel.get_bone_pose_position(hips_idx).is_equal_approx(
		hips_rest.origin + Vector3(0.125, -0.05, 0.2)),
		role + " root offset must be applied exactly once")
	_expect(skel.get_bone_pose_position(arm_idx).is_equal_approx(arm_rest.origin),
		role + " non-root translation cannot stretch bone lengths")
	_expect(skel.get_bone_pose_position(neutral).is_equal_approx(neutral_position)
		and absf(skel.get_bone_pose_rotation(neutral).dot(neutral_rotation)) > 0.99999
		and skel.get_bone_pose_scale(neutral).is_equal_approx(neutral_scale),
		role + " neutral import bone must not be overwritten")

	var before := skel.get_bone_pose_rotation(arm_idx)
	var bad := pose.duplicate(true)
	bad["rotations"].erase("head")
	var rejected: Dictionary = driver.call("apply_pose", bad)
	_expect(not rejected.get("error", "").is_empty(), role + " incomplete native pose is rejected")
	_expect(absf(skel.get_bone_pose_rotation(arm_idx).dot(before)) > 0.99999,
		role + " invalid native pose cannot partially write a skeleton")
	model.free()

func _check_layer(role: String, glb: String, input: String, face: int, yaw: float) -> void:
	var motion: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(input))
	var layer: Node2D = LayerScript.new()
	root.add_child(layer)
	layer.call("configure", role, glb, yaw, false)
	_expect(layer.call("setup", motion), role + " presentation layer loads")
	_expect(layer.has_method("apply_visual") and layer.has_method("set_facing"),
		role + " layer lacks native pose/facing interface")
	if not layer.has_method("apply_visual") or not layer.has_method("set_facing"):
		layer.free()
		return
	var pose := _pose(motion["bones"])
	layer.call("apply_visual", {"pose": pose, "facing": face, "canvas_tilt": 0.12})
	var driver: RefCounted = layer.get("drv")
	var skel: Skeleton3D = driver.get("skel")
	var arm := skel.find_bone("forearm_f")
	_expect(layer.has_method("anchor_offset"), role + " lacks a pure presented contact anchor")
	if layer.has_method("anchor_offset"):
		var next_pose := pose.duplicate(true)
		var bend := Quaternion(Vector3.RIGHT, 0.25)
		next_pose.rotations.forearm_f = [bend.x,bend.y,bend.z,bend.w]
		next_pose.root_offset = [0.12,-0.05,0.2]
		var before := skel.get_bone_pose_rotation(arm)
		var predicted: Vector2 = layer.call("anchor_offset",next_pose,"lead_hand",face,0.12)
		_expect(absf(skel.get_bone_pose_rotation(arm).dot(before)) > 0.99999,
			role + " contact prediction cannot overwrite the displayed pose")
		layer.call("apply_visual",{"pose":next_pose,"facing":face,"canvas_tilt":0.12})
		var endpoint: Array = motion.apose_points.f_hand
		var rest_point := Vector3(endpoint[0],endpoint[1],0.0)
		var in_bone := skel.get_bone_global_rest(arm).affine_inverse() * rest_point
		var world_point := skel.global_transform * (skel.get_bone_global_pose(arm) * in_bone)
		var camera: Camera3D = layer.get("cam")
		var viewport: SubViewport = layer.get("sv")
		var pixel := camera.unproject_position(world_point)
		var floor_pixel := camera.unproject_position(Vector3.ZERO)
		var sx := 1.22 if bool(layer.get("foe_visual")) else 1.0
		var sy := 0.94 if bool(layer.get("foe_visual")) else 1.0
		var actual := Vector2((pixel.x-viewport.size.x*.5)*.45*sx,
			(pixel.y-floor_pixel.y)*.45*sy).rotated(.12)
		_expect(predicted.distance_to(actual) < 0.01,
			role + " predicted anchor must match real posed skeleton/camera/scale/root")
		_expect(predicted.length() > 20.0, role + " anchor cannot silently collapse to origin")
		layer.call("apply_visual",{"pose":pose,"facing":face,"canvas_tilt":.12})
	_expect(absf(skel.get_bone_pose_rotation(arm).dot(
		skel.get_bone_rest(arm).basis.get_rotation_quaternion())) > 0.99999,
		role + " native pose cannot receive the old +/-50 degree guard twice")
	_expect(is_equal_approx(layer.rotation, 0.12), role + " 3D canvas recoil tilt is applied")
	var model: Node3D = layer.get("model_root")
	_expect(model != null, role + " facing must operate on the imported model")
	if model != null:
		var initial := model.transform
		layer.call("set_facing", -face)
		_expect(model.transform.basis.is_equal_approx(Basis(Vector3.UP, PI) * initial.basis),
			role + " reversing facing rotates the model 180 degrees around Y")
		layer.call("set_facing", face)
		_expect(model.transform.is_equal_approx(initial), role + " facing switches must not accumulate")
		_expect(absf(skel.get_bone_pose_rotation(arm).dot(
			skel.get_bone_rest(arm).basis.get_rotation_quaternion())) > 0.99999,
			role + " facing cannot mirror or overwrite bone-local quaternions")
	layer.free()

func _run() -> void:
	_check_role("player", "res://assets/3d/player-rigged.glb", "res://data/motion_input.json")
	_check_role("foe", "res://assets/3d/foe-rigged.glb", "res://data/motion_input_foe.json")
	_check_layer("player", "res://assets/3d/player-rigged.glb", "res://data/motion_input.json", 1, -55.0)
	_check_layer("foe", "res://assets/3d/foe-rigged.glb", "res://data/motion_input_foe.json", -1, 55.0)
	for failure in failures:
		print("FAIL: ", failure)
	print("NATIVE_RIG_CHECK: %s (%d checks, %d failures)" % [
		"PASS" if failures.is_empty() else "FAIL", checks, failures.size()])
	quit(0 if failures.is_empty() else 1)
