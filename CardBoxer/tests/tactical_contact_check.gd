extends SceneTree
const Arena = preload("res://scripts/arena.gd")
var a
func _initialize() -> void:
	OS.set_environment("CARD_BOXER_BATTLE_MODE","tactical")
	OS.set_environment("CARD_BOXER_3D","1")
	call_deferred("run")
func run() -> void:
	a = Arena.new()
	root.add_child(a)
	a.set_process(false)
	await process_frame
	if not a._native_active():
		print("FAIL: native rig unavailable")
		quit(1)
		return
	var m = a.tactical
	m.state.distance = 0
	m.player_plan = ["sidestep","jab","backstep","guard","focus"]
	m.enemy_plan = ["uppercut","cross","guard","focus","rush"]
	m._begin_resolve()
	var contact_at := -1.0
	for entry in m._schedule:
		if entry.kind=="contact":
			for hit in entry.group.hits:
				if hit.source=="player" and hit.kind=="punish":
					contact_at = float(entry.at)
	if contact_at<0.0:
		print("FAIL: fixture must produce a real riposte contact")
		a.free()
		quit(1)
		return
	a._process(contact_at)
	var pv: Dictionary = a.last_visuals.player
	var ev: Dictionary = a.last_visuals.foe
	var fist: Vector2 = a.player.position+pv.canvas_shift+a.layer_3d.anchor_offset(pv.pose,"lead_hand",1,pv.canvas_tilt)
	var head: Vector2 = a.enemy.position+ev.canvas_shift+a.layer_3d_foe.anchor_offset(ev.pose,"head",-1,ev.canvas_tilt)
	var chest: Vector2 = a.enemy.position+ev.canvas_shift+a.layer_3d_foe.anchor_offset(ev.pose,"chest",-1,ev.canvas_tilt)
	var ratio := clampf((fist.y-head.y)/(chest.y-head.y),0.0,1.0) if absf(chest.y-head.y)>0.001 else 0.5
	var body: Vector2 = head.lerp(chest,ratio)
	var dx := absf(fist.x-body.x)
	print("TACTICAL CONTACT: dx=%.3f fist=%s body=%s" % [dx,str(fist),str(body)])
	a.free()
	print("TACTICAL CONTACT CHECK: %d/1 passed" % (1 if dx<=12.0 else 0))
	quit(0 if dx<=12.0 else 1)
