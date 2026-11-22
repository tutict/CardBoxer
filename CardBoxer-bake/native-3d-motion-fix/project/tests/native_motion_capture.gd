extends SceneTree
## Native library -> production Fighter3DLayer, real GL only. No gameplay claims.
const LayerScript = preload("res://scripts/fighter_3d_layer.gd")
var out_dir: String
var rows: Array = []
var motion_source_sha256 := ""
var source_sha256: Dictionary = {}

func _initialize() -> void:
	call_deferred("_run")

func _write(payload: Dictionary) -> void:
	payload["motion_source_sha256"] = motion_source_sha256
	payload["source_sha256"] = source_sha256
	var file := FileAccess.open(out_dir + "/manifest.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(payload, "\t"))
	file.close()

func _run() -> void:
	out_dir = OS.get_environment("NATIVE_CAPTURE_OUT")
	if out_dir.is_empty():
		out_dir = ProjectSettings.globalize_path("res://../shots/native-motion")
	DirAccess.make_dir_recursive_absolute(out_dir)
	if DisplayServer.get_name() == "headless":
		_write({"error": "A real GL Compatibility renderer is required; headless/dummy images are invalid"})
		quit(2)
		return
	if not FileAccess.file_exists("res://scripts/native_motion.gd"):
		_write({"error": "NativeMotion is not ready"})
		quit(2)
		return
	for source in ["data/combat_motion_3d.json", "scripts/native_motion.gd", "scripts/rig_driver.gd",
		"scripts/fighter_3d_layer.gd", "assets/3d/player-rigged.glb", "assets/3d/foe-rigged.glb"]:
		source_sha256[source] = FileAccess.get_sha256("res://" + String(source))
	var library = load("res://scripts/native_motion.gd").new()
	motion_source_sha256 = FileAccess.get_sha256("res://data/combat_motion_3d.json")
	if not library.load_data():
		_write({"error": "NativeMotion data is not ready"})
		quit(2)
		return
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/combat_motion_3d.json"))
	var layers: Dictionary = {}
	for role in ["player", "foe"]:
		var layer = LayerScript.new()
		root.add_child(layer)
		layer.configure(role, "res://assets/3d/" + String(role) + "-rigged.glb",
			LayerScript.DEFAULT_SIDE_YAW if role == "player" else LayerScript.DEFAULT_FOE_YAW, false)
		var legacy_path: String = "res://data/motion_input.json" if role == "player" else "res://data/motion_input_foe.json"
		var legacy: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(legacy_path))
		if not layer.setup(legacy) or not layer.has_method("apply_visual"):
			_write({"error": "Fighter3DLayer native apply_visual/setup is not ready", "role": role})
			quit(2)
			return
		layers[role] = layer
	await process_frame
	await RenderingServer.frame_post_draw
	var requested := OS.get_environment("NATIVE_CAPTURE_CLIPS")
	var clips: Array = Array(requested.split(",")) if not requested.is_empty() else ["stance", "jab", "cross", "sweep"]
	if requested == "all":
		clips = data.roles.player.clips.keys()
	var swaps := OS.get_environment("NATIVE_CAPTURE_FACING") == "both"
	var facings: Array = [1, -1] if swaps else [1]
	for clip_value in clips:
		var clip: String = String(clip_value).strip_edges()
		for relative_facing in facings:
			var frames := maxi(int(library.clip_frames("player", clip)), int(library.clip_frames("foe", clip)))
			var samples: Array = []
			for frame in range(frames):
				samples.append(float(frame))
			# Fractional samples at authored keys and contact boundaries expose interpolation.
			for role in ["player", "foe"]:
				if not data.roles[role].clips.has(clip):
					continue
				for key in data.roles[role].clips[clip]["keys"]:
					var f := float(key.frame)
					for offset in [-0.5, 0.0, 0.5]:
						var value := clampf(f + float(offset), 0, frames - 1)
						if not samples.has(value):
							samples.append(value)
				samples.sort()
			for sample_value in samples:
				var f := float(sample_value)
				for role in ["player", "foe"]:
					var facing: int = int(relative_facing) * (1 if role == "player" else -1)
					layers[role].apply_visual({"pose": library.sample(role, clip, f), "facing": facing, "canvas_tilt": 0.0})
				await process_frame
				await RenderingServer.frame_post_draw
				for role in ["player", "foe"]:
					var layer = layers[role]
					var file_name := "%s-%s-facing%d-f%05.1f.png" % [role, clip, int(relative_facing), f]
					var path := out_dir + "/" + file_name
					var image: Image = layer.sv.get_texture().get_image()
					var error := image.save_png(path)
					var key_frames: Array = []
					for key in data.roles[role].clips[clip]["keys"]:
						key_frames.append(float(key.frame))
					rows.append({"role": role, "clip": clip, "frame": f, "path": path, "png_error": error,
						"facing": int(relative_facing) * (1 if role == "player" else -1),
						"relative_facing": relative_facing, "authored_key": key_frames.has(f),
						"contact_frame": library.contact_frame(role, clip),
						"camera_yaw": layer.view_yaw_deg, "geometry_origin": "current imported GLB",
						"native_pose": library.sample(role, clip, f)})
			_write({"renderer": RenderingServer.get_video_adapter_name(), "display_server": DisplayServer.get_name(),
				"clips": clips, "rows": rows, "completed": false})
		print("NATIVE_CAPTURE_CLIP " + clip)
	_write({"renderer": RenderingServer.get_video_adapter_name(), "display_server": DisplayServer.get_name(),
		"clips": clips, "rows": rows, "completed": true, "evidence": "Direct native pose capture; excludes gameplay integration"})
	print("NATIVE_CAPTURE_READY " + out_dir + " count=" + str(rows.size()))
	quit(0)
