extends SceneTree
## Real imported meshes at phase and fractional boundaries, both roles/facings.
const Layer = preload("res://scripts/fighter_3d_layer.gd")
const Motion = preload("res://scripts/native_motion.gd")
var rows: Array = []

func _initialize() -> void: call_deferred("run")

func run() -> void:
	var output := OS.get_environment("RETOPO_CAPTURE_OUT")
	if output=="" or DisplayServer.get_name()=="headless":
		print("FAIL: RETOPO_CAPTURE_OUT and a real renderer are required")
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(output)
	var library = Motion.new()
	if not library.load_data():
		print("FAIL: ",library.last_error)
		quit(1)
		return
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/combat_motion_3d.json"))
	var layers := {}
	for role: String in ["player","foe"]:
		var layer = Layer.new()
		root.add_child(layer)
		layer.configure(role,"res://assets/3d/"+role+"-rigged.glb",Layer.DEFAULT_SIDE_YAW if role=="player" else Layer.DEFAULT_FOE_YAW,false)
		var path := "res://data/motion_input.json" if role=="player" else "res://data/motion_input_foe.json"
		if not layer.setup(JSON.parse_string(FileAccess.get_file_as_string(path))):
			print("FAIL: actual imported layer setup ",role)
			quit(1)
			return
		layers[role]=layer
	var clips: Array = data.roles.player.clips.keys()
	for clip: String in clips:
		var samples: Array = []
		for role: String in ["player","foe"]:
			var entry: Dictionary = data.roles[role].clips[clip]
			var end := float(int(entry.frames)-1)
			var windup := float(entry.split[0])
			var contact := float(entry.contact_frame)
			var phase_samples := [0.0,end,windup*.5,maxf(0.0,windup-1.0),windup,contact,contact+.5,(maxf(0.0,contact)+end)*.5]
			if clip=="ko": phase_samples.append_array([end*.15,end*.30,end*.60])
			for value: float in phase_samples:
				var at := clampf(value,0.0,end)
				if not samples.has(at): samples.append(at)
		samples.sort()
		for relative: int in [1,-1]:
			for at: float in samples:
				var visuals := {}
				for role: String in ["player","foe"]:
					var facing := relative*(1 if role=="player" else -1)
					var pose: Dictionary = library.sample(role,clip,at)
					visuals[role]={"pose":pose,"facing":facing,"canvas_tilt":0.0}
					layers[role].apply_visual(visuals[role])
				await process_frame
				await RenderingServer.frame_post_draw
				for role: String in ["player","foe"]:
					var layer = layers[role]
					var path := output.path_join("%s-%s-facing%d-frame%06.2f.png" % [role,clip,relative,at])
					var error: int = layer.sv.get_texture().get_image().save_png(path)
					if error!=OK:
						print("FAIL: image write ",path)
						quit(1)
						return
					rows.append({"role":role,"clip":clip,"frame":at,"relative_facing":relative,
						"facing":visuals[role].facing,"path":path,"png_error":error,
						"hand_grip":visuals[role].pose.hand_grip,"native_pose":visuals[role].pose,
						"contact_frame":library.contact_frame(role,clip),"camera_yaw":layer.view_yaw_deg})
		print("RETOPO_MOTION_CLIP: ",clip," phases=",samples.size()," both facings")
	var hashes := {}
	for path: String in ["assets/3d/player-rigged.glb","assets/3d/foe-rigged.glb","data/combat_motion_3d.json","data/model_profile_3d.json","scripts/native_motion.gd","scripts/hand_shape.gd","scripts/fighter_3d_layer.gd"]:
		hashes[path]=FileAccess.get_sha256("res://"+path)
	var file := FileAccess.open(output.path_join("manifest.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify({"completed":true,"renderer":RenderingServer.get_video_adapter_name(),
		"display_server":DisplayServer.get_name(),"clips":clips,"roles":["player","foe"],"relative_facings":[1,-1],
		"source_sha256":hashes,"rows":rows,"evidence":"Real canonical skin/morph render at phase and fractional boundaries. Gameplay events are checked separately."},"\t"))
	file.close()
	for layer in layers.values(): layer.free()
	print("RETOPO_MOTION_RENDER: ",rows.size()," actual images")
	quit(0)
