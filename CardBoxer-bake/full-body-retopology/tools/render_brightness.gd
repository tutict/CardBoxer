extends SceneTree
## Same camera/light pose, measuring the actual local canvas composite.
const Layer = preload("res://scripts/fighter_3d_layer.gd")
const Motion = preload("res://scripts/native_motion.gd")

func _initialize() -> void: call_deferred("run")

func brightness(image: Image) -> Dictionary:
	var sum := 0.0
	var count := 0
	for y in range(image.get_height()):
		for x in range(image.get_width()):
			var color := image.get_pixel(x,y)
			if color.a>.94:
				sum+=(color.r*.2126+color.g*.7152+color.b*.0722)*255.0
				count+=1
	return {"foreground_pixels":count,"mean_luma":sum/maxi(count,1)}

func run() -> void:
	var output := OS.get_environment("RETOPO_CAPTURE_OUT")
	if output=="" or DisplayServer.get_name()=="headless":
		print("FAIL: brightness requires a real renderer and output directory")
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(output)
	var layers := {}
	var views := {}
	var rotations := {}
	for bone: String in Motion.BONES: rotations[bone]=[0.0,0.0,0.0,1.0]
	var pose := {"rotations":rotations,"root_offset":[0.0,0.0,0.0],"hand_grip":[.75,.75],"clip_id":"rest","frame":0.0}
	for role: String in ["player","foe"]:
		var view := SubViewport.new()
		view.size=Vector2i(1024,1024)
		view.world_2d=World2D.new()
		view.transparent_bg=true
		view.render_target_update_mode=SubViewport.UPDATE_ALWAYS
		root.add_child(view)
		var layer = Layer.new()
		view.add_child(layer)
		layer.configure(role,"res://assets/3d/"+role+"-rigged.glb",0.0,false)
		var path := "res://data/motion_input.json" if role=="player" else "res://data/motion_input_foe.json"
		if not layer.setup(JSON.parse_string(FileAccess.get_file_as_string(path))):
			print("FAIL: brightness layer setup ",role)
			quit(1)
			return
		layer.position=Vector2(512,900)
		layer.scale=Vector2(4,4)
		layer.set_foe_visual(false)
		layer.apply_visual({"pose":pose,"facing":1 if role=="player" else -1,"canvas_tilt":0.0})
		layers[role]=layer
		views[role]=view
	for frame in range(4):
		await process_frame
		await RenderingServer.frame_post_draw
	var player_plain: Image=views.player.get_texture().get_image()
	var foe_plain: Image=views.foe.get_texture().get_image()
	player_plain.save_png(output.path_join("player-same-view.png"))
	foe_plain.save_png(output.path_join("foe-plain-same-view.png"))
	layers.foe.set_foe_visual(true)
	for frame in range(4):
		await process_frame
		await RenderingServer.frame_post_draw
	var player_after: Image=views.player.get_texture().get_image()
	var foe_after: Image=views.foe.get_texture().get_image()
	player_after.save_png(output.path_join("player-after-foe-toggle.png"))
	foe_after.save_png(output.path_join("foe-composite-same-view.png"))
	var player_metrics:=brightness(player_after)
	var foe_metrics:=brightness(foe_after)
	var ratio: float=foe_metrics.mean_luma/maxf(player_metrics.mean_luma,.0001)
	var same_player: bool=player_plain.get_data()==player_after.get_data()
	var payload := {"ok":ratio>=.5 and ratio<=.75 and same_player,"player":player_metrics,
		"foe":foe_metrics,"foe_plain":brightness(foe_plain),"foe_player_ratio":ratio,
		"player_unchanged_by_foe_toggle":same_player,"renderer":RenderingServer.get_video_adapter_name(),
		"display_server":DisplayServer.get_name(),"camera_yaw":0.0,"pose":"canonical rest, hand .75",
		"canvas_shader":Layer.FOE_CANVAS_SHADER_CODE,"source_sha256":{}}
	for path: String in ["assets/3d/player-rigged.glb","assets/3d/foe-rigged.glb","scripts/fighter_3d_layer.gd"]:
		payload.source_sha256[path]=FileAccess.get_sha256("res://"+path)
	var file:=FileAccess.open(output.path_join("brightness.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify(payload,"\t"))
	file.close()
	print("RETOPO_BRIGHTNESS: ratio=",ratio," player_unchanged=",same_player)
	quit(0 if payload.ok else 1)
