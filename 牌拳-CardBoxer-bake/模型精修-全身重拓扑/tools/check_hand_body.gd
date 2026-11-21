extends SceneTree
## Compare all integer/fractional body samples with the immutable V2 implementation.
const Motion = preload("res://scripts/native_motion.gd")
var checks := 0
var failures: Array[String] = []
var max_root_error := 0.0
var max_rotation_error := 0.0

func _initialize() -> void: call_deferred("run")

func expect(ok: bool,label: String) -> void:
	checks+=1
	if not ok and failures.size()<24: failures.append(label)

func quaternion(values: Array) -> Quaternion:
	return Quaternion(float(values[0]),float(values[1]),float(values[2]),float(values[3]))

func run() -> void:
	var baseline_root:=String(get_script().resource_path).get_base_dir().path_join("../baseline").simplify_path()
	var original_script=load(baseline_root.path_join("scripts/native_motion.gd"))
	if original_script==null:
		print("FAIL: immutable original body sampler unavailable")
		quit(1)
		return
	var before=original_script.new()
	var after=Motion.new()
	expect(before.load_data(baseline_root.path_join("data/combat_motion_3d.json")),"immutable V2 body library loads")
	expect(after.load_data(),"hand-aware candidate library loads")
	if not failures.is_empty():
		for failure in failures: print("FAIL: ",failure)
		quit(1)
		return
	var data: Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/combat_motion_3d.json"))
	var samples := 0
	for role: String in ["player","foe"]:
		for clip: String in data.roles[role].clips:
			var frames:=int(data.roles[role].clips[clip].frames)
			for step in range(maxi(1,frames*2-1)):
				var at:=float(step)*.5
				var old_pose: Dictionary=before.sample(role,clip,at)
				var new_pose: Dictionary=after.sample(role,clip,at)
				var label:=role+" "+clip+" frame "+str(at)
				for bone: String in Motion.BONES:
					var error:=1.0-absf(quaternion(old_pose.rotations[bone]).normalized().dot(quaternion(new_pose.rotations[bone]).normalized()))
					max_rotation_error=maxf(max_rotation_error,error)
					expect(error<=.000001,label+" body rotation "+bone)
				for axis in range(3):
					var error:=absf(float(old_pose.root_offset[axis])-float(new_pose.root_offset[axis]))
					max_root_error=maxf(max_root_error,error)
					expect(error<=.000001,label+" root axis "+str(axis))
				samples+=1
	for failure in failures: print("FAIL: ",failure)
	print("HAND BODY INVARIANCE CHECK: %d checks, %d samples, failures=%d rotation_dot_error=%f root_error_m=%f" % [checks,samples,failures.size(),max_rotation_error,max_root_error])
	quit(0 if failures.is_empty() else 1)
