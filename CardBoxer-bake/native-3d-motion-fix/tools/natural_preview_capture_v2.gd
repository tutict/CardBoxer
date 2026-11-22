extends SceneTree
## Tools-only preview: production Presentation clocks/poses, isolated dual attackers.
const Motion = preload("res://scripts/native_motion.gd")
const Flow = preload("res://scripts/battle_presentation.gd")
const Layer = preload("res://scripts/fighter_3d_layer.gd")
var rows: Array = []

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var out_dir := OS.get_environment("NATURAL_PREVIEW_OUT")
	DirAccess.make_dir_recursive_absolute(out_dir)
	if DisplayServer.get_name() == "headless":
		push_error("Preview requires a real renderer")
		quit(2)
		return
	var library = Motion.new()
	if not library.load_data():
		push_error(library.last_error)
		quit(2)
		return
	var layers := {}
	var flows := {}
	var snapshots := {}
	var context := {"mode":"taikou"}
	for role: String in ["player","foe"]:
		var layer = Layer.new()
		root.add_child(layer)
		layer.configure(role,"res://assets/3d/"+role+"-rigged.glb",Layer.DEFAULT_SIDE_YAW if role=="player" else Layer.DEFAULT_FOE_YAW,false)
		var legacy_path := "res://data/motion_input.json" if role=="player" else "res://data/motion_input_foe.json"
		if not layer.setup(JSON.parse_string(FileAccess.get_file_as_string(legacy_path))):
			quit(2)
			return
		layers[role]=layer
		var flow = Flow.new()
		flow.setup(library)
		flows[role]=flow
		snapshots[role]={"state":0,"action_seq":1,"facing":1 if role=="player" else -1}
	await process_frame
	var clips := ["jab","cross","sweep","uppercut","wave"]
	for clip: String in clips:
		for role: String in ["player","foe"]:
			flows[role].reset(1)
			flows[role].begin_exchange({"round_id":1,"actor":role,"winner":role,"clip_id":clip,"action_seq":1,"approach_extra_x":280.0 if role=="player" else -280.0})
		for step in range(83):
			var visuals := {}
			for role: String in ["player","foe"]:
				if step>0: flows[role].advance(1.0/60.0,context)
				visuals[role]=flows[role].sample(role,snapshots[role],context)
				layers[role].apply_visual(visuals[role])
			await process_frame
			await RenderingServer.frame_post_draw
			for role: String in ["player","foe"]:
				var path := out_dir+"/"+clip+"-f%03d-"%step+role+".png"
				var image: Image=layers[role].sv.get_texture().get_image()
				var error:=image.save_png(path)
				rows.append({"clip":clip,"step":step,"time":float(step)/60.0,"role":role,"path":path,"png_error":error,"native_frame":visuals[role].frame,"native_clip":visuals[role].clip_id,"frozen":visuals[role].frozen,"exchange_time":flows[role].exchange_time,"canvas_shift":[visuals[role].canvas_shift.x,visuals[role].canvas_shift.y]})
		print("NATURAL_PREVIEW_CLIP ",clip)
	var hashes := {}
	for source: String in ["data/combat_motion_3d.json","scripts/native_motion.gd","scripts/battle_presentation.gd","scripts/fighter_3d_layer.gd","assets/3d/player-rigged.glb","assets/3d/foe-rigged.glb"]:
		hashes[source]=FileAccess.get_sha256("res://"+source)
	var file:=FileAccess.open(out_dir+"/manifest.json",FileAccess.WRITE)
	file.store_string(JSON.stringify({"completed":true,"renderer":RenderingServer.get_video_adapter_name(),"display_server":DisplayServer.get_name(),"source_sha256":hashes,"source_fps":60,"steps_per_clip":83,"clips":clips,"rows":rows,"evidence":"Isolated simultaneous actor previews sampled by production Presentation.advance/sample. Local boot gait is shown; viewport framing omits canvas translation. Actual translated gameplay is covered separately by live scenarios and root normal match."},"\t"))
	file.close()
	print("NATURAL_PREVIEW_READY ",out_dir," rows=",rows.size())
	quit(0)
