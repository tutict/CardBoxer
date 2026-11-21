extends SceneTree
const Motion = preload("res://scripts/native_motion.gd")
const Flow = preload("res://scripts/battle_presentation.gd")
const Arena = preload("res://scripts/arena.gd")
var library
var flows := {}
var snapshots := {}
var context := {"mode":"taikou"}
var arena
var render_start := 0
var measured_start := 0
var last_frame := 0
var frame_intervals := []
var role_times := {"player":[],"foe":[]}

func _initialize() -> void:
	call_deferred("_run")

func stats(values: Array) -> Dictionary:
	var sorted := values.duplicate()
	sorted.sort()
	var sum := 0.0
	for value in values: sum += float(value)
	return {"count":values.size(),"mean_us":sum/maxi(values.size(),1),"p50_us":sorted[int(sorted.size()*.5)],"p95_us":sorted[mini(sorted.size()-1,int(sorted.size()*.95))],"max_us":sorted[-1]}

func _run() -> void:
	library = Motion.new()
	if not library.load_data():
		push_error(library.last_error)
		quit(1)
		return
	for role: String in ["player","foe"]:
		var flow = Flow.new()
		var setup_start := Time.get_ticks_usec()
		flow.setup(library)
		print("SETUP PREPARE SUPPORT ",role," us=",Time.get_ticks_usec()-setup_start)
		flow.reset(1)
		flow.begin_exchange({"round_id":1,"actor":role,"winner":role,"clip_id":"jab","action_seq":1,"approach_extra_x":280.0 if role=="player" else -280.0})
		flows[role] = flow
		snapshots[role] = {"state":0,"action_seq":1,"facing":1 if role=="player" else -1}
		flow.exchange_time = .2
		var cold_start := Time.get_ticks_usec()
		flow.sample(role,snapshots[role],context)
		print("COLD SAMPLE ",role," us=",Time.get_ticks_usec()-cold_start)
	var timings := {"player":[],"foe":[]}
	var support_times := {"player":[],"foe":[]}
	for step in range(480):
		var time := fposmod(float(step)/60.0,Flow.ATTACK_S)
		for role: String in ["player","foe"]:
			flows[role].exchange_time = time
			var start := Time.get_ticks_usec()
			var pose: Dictionary = flows[role].sample(role,snapshots[role],context).pose
			timings[role].append(Time.get_ticks_usec()-start)
			start = Time.get_ticks_usec()
			library.preserve_support(role,pose,pose)
			support_times[role].append(Time.get_ticks_usec()-start)
	for role: String in ["player","foe"]:
		print("CPU SAMPLE ",role," ",JSON.stringify(stats(timings[role])))
		print("CPU PRESERVE SUPPORT ",role," ",JSON.stringify(stats(support_times[role])))
	if DisplayServer.get_name()=="headless":
		quit(0)
		return
	arena = Arena.new()
	root.add_child(arena)
	arena.set_process(false)
	Engine.max_fps = 60 if OS.get_environment("NATURAL_BENCH_CAP")=="60" else 0
	render_start = Time.get_ticks_usec()
	last_frame = render_start
	process_frame.connect(_render_frame)
	print("RENDER START driver=",RenderingServer.get_current_rendering_driver_name()," display=",DisplayServer.get_name()," cap=",Engine.max_fps)

func _render_frame() -> void:
	var now := Time.get_ticks_usec()
	var elapsed := float(now-render_start)/1000000.0
	if elapsed>1.0:
		if measured_start==0: measured_start = now
		else: frame_intervals.append(now-last_frame)
	last_frame = now
	for role: String in ["player","foe"]:
		flows[role].exchange_time = fposmod(elapsed,Flow.ATTACK_S)
		var start := Time.get_ticks_usec()
		var visual: Dictionary = flows[role].sample(role,snapshots[role],context)
		if measured_start>0: role_times[role].append(Time.get_ticks_usec()-start)
		var fighter = arena.player if role=="player" else arena.enemy
		var layer = arena.layer_3d if role=="player" else arena.layer_3d_foe
		layer.position = fighter.position+visual.canvas_shift
		layer.apply_visual(visual)
	if elapsed>=8.0:
		var seconds := float(now-measured_start)/1000000.0
		print("REAL RENDER FPS ",JSON.stringify({"frames":frame_intervals.size(),"seconds":seconds,"fps":float(frame_intervals.size())/seconds,"frame_intervals":stats(frame_intervals)}))
		for role: String in ["player","foe"]: print("RENDER SAMPLE ",role," ",JSON.stringify(stats(role_times[role])))
		quit(0)
