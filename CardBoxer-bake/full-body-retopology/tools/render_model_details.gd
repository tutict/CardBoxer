extends SceneTree
## Same real Godot camera/light rig for archived and canonical new geometry.
const Layer = preload("res://scripts/fighter_3d_layer.gd")
const Driver = preload("res://scripts/rig_driver.gd")
const Motion = preload("res://scripts/native_motion.gd")
const Hands = preload("res://scripts/hand_shape.gd")
var output := ""
var rows: Array = []

func _initialize() -> void: call_deferred("run")

func build(role: String, path: String, profile: Dictionary):
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	var error := document.append_from_file(path,state)
	if error!=OK:
		push_error("Cannot read model for real renderer: "+path)
		return null
	var scene = document.generate_scene(state)
	if scene==null: return null
	var layer = Layer.new()
	layer.role_id = role
	layer.glb_path = path
	root.add_child(layer)
	layer.sv = SubViewport.new()
	layer.sv.size = Vector2i(1024,1024)
	layer.sv.transparent_bg = true
	layer.sv.own_world_3d = true
	layer.sv.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	layer.add_child(layer.sv)
	layer.sv.add_child(scene)
	layer.model_root = scene
	layer.imported_model_transform = scene.transform
	layer._collect_meshes(scene)
	var rig = layer._find_skel(scene)
	var legacy_path := "res://data/motion_input.json" if role=="player" else "res://data/motion_input_foe.json"
	var legacy: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(legacy_path))
	layer.motion = legacy
	layer.drv = Driver.new()
	if rig==null or not layer.drv.setup(rig,legacy):
		layer.free()
		return null
	layer._hand_profile = profile
	layer.cam = Camera3D.new()
	layer.cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	layer.cam.current = true
	layer.cam.near = .05
	layer.cam.far = 100.0
	layer.sv.add_child(layer.cam)
	layer._add_light(Vector3(-38,-32,0),1.9,Color(1,.96,.90),true)
	layer._add_light(Vector3(-20,145,0),.75,Color(.68,.79,1),false)
	layer._add_light(Vector3(-12,75,0),.55,Color(1,.85,.70),false)
	layer._add_light(Vector3(-25,200,0),.95,Color(.76,.85,1),false)
	return layer

func identity_pose(grip: float) -> Dictionary:
	var rotations := {}
	for bone: String in Motion.BONES: rotations[bone] = [0.0,0.0,0.0,1.0]
	return {"rotations":rotations,"root_offset":[0.0,0.0,0.0],"hand_grip":[grip,grip],"clip_id":"rest","frame":0.0}

func camera(layer, feature: String, yaw: float) -> void:
	var point := Vector3(0,.84,0)
	var size := 2.3
	if feature=="face":
		point = layer.drv.global_rest.head.origin+Vector3(0,.055,.05)
		size = .45 if layer.role_id=="player" else .65
	elif feature=="hand_front" or feature=="hand_rear":
		var key := "f_hand" if feature=="hand_front" else "b_hand"
		var endpoint: Array = layer.motion.apose_points[key]
		point = Vector3(float(endpoint[0]),float(endpoint[1]),0.0)+Vector3(0,.025,.04)
		size = .36 if layer.role_id=="player" else .48
	var world: Vector3 = layer.drv.skel.global_transform*point
	var angle := deg_to_rad(yaw)
	layer.cam.size = size
	layer.cam.position = world+Vector3(3.55*sin(angle),.12,3.55*cos(angle))
	layer.cam.look_at(world,Vector3.UP)

func save(layer, role: String, kind: String, feature: String, yaw: float, grip: float) -> void:
	layer.apply_visual({"pose":identity_pose(grip),"facing":1 if role=="player" else -1,"canvas_tilt":0.0})
	camera(layer,feature,yaw)
	await process_frame
	await RenderingServer.frame_post_draw
	var path := output.path_join("%s-%s-%s-yaw%d-grip%03d.png" % [role,kind,feature,int(yaw),roundi(grip*100)])
	var error: int = layer.sv.get_texture().get_image().save_png(path)
	var values := []
	for entry: Dictionary in layer._hand_meshes:
		var hand_values := []
		for index: int in entry.indices: hand_values.append(entry.mi.get_blend_shape_value(index))
		values.append(hand_values)
	rows.append({"role":role,"kind":kind,"feature":feature,"yaw":yaw,"hand_grip":grip,
		"path":path,"png_error":error,"model_sha256":FileAccess.get_sha256(layer.glb_path),
		"camera_transform":str(layer.cam.transform),"ortho_size":layer.cam.size,
		"actual_morph_values":values,"bones":layer.drv.skel.get_bone_count()})

func run() -> void:
	output = OS.get_environment("MODEL_DETAIL_OUT")
	if output=="" or DisplayServer.get_name()=="headless":
		print("FAIL: real renderer and MODEL_DETAIL_OUT are required")
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(output)
	var profiles: Dictionary = {}
	if FileAccess.file_exists("res://data/model_profile_3d.json"):
		profiles = JSON.parse_string(FileAccess.get_file_as_string("res://data/model_profile_3d.json")).roles
	var baseline_only := OS.get_environment("MODEL_DETAIL_BASELINE_ONLY")=="1"
	for role: String in ["player","foe"]:
		var kinds := ["baseline"] if baseline_only else ["baseline","candidate"]
		for kind: String in kinds:
			var path := ProjectSettings.globalize_path("res://../baseline/assets/3d/"+role+"-rigged.glb") if kind=="baseline" else ProjectSettings.globalize_path("res://assets/3d/"+role+"-rigged.glb")
			var layer = build(role,path,profiles.get(role,{}) if kind=="candidate" else {})
			if layer==null:
				print("FAIL: detail layer ",role," ",kind)
				quit(1)
				return
			await save(layer,role,kind,"full",0.0,.0)
			await save(layer,role,kind,"full",35.0 if role=="player" else -35.0,.0)
			await save(layer,role,kind,"face",0.0,.0)
			await save(layer,role,kind,"face",35.0,.0)
			for feature: String in ["hand_front","hand_rear"]:
				for grip: float in [.0,.25,.5,.75,1.0]:
					await save(layer,role,kind,feature,0.0,grip)
			layer.free()
	var file := FileAccess.open(output.path_join("manifest.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify({"completed":true,"renderer":RenderingServer.get_video_adapter_name(),
		"display_server":DisplayServer.get_name(),"rows":rows},"\t"))
	file.close()
	print("MODEL_DETAIL_RENDER: ",rows.size()," real images")
	quit(0)
