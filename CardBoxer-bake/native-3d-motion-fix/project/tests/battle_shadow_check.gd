extends SceneTree
const ArenaScript = preload("res://scripts/arena.gd")
var draws := 0

func _initialize() -> void:
	OS.set_environment("CARD_BOXER_3D","1")
	OS.set_environment("CARD_BOXER_BATTLE_MODE","taikou")
	call_deferred("_run")

func _run() -> void:
	var a = ArenaScript.new()
	root.add_child(a)
	a.set_process(false)
	a.battle_mode = "taikou"
	a.player.draw.connect(func(): draws += 1)
	for frame in range(3): await process_frame
	var initial_draws := draws
	a.presentation.begin_exchange({"round_id":a._round_serial,"winner":"player","actor":"player","target":"foe","clip_id":"jab","action_seq":1})
	a._advance_presentation(0.24)
	a._sync_3d_layer()
	for frame in range(3): await process_frame
	var ok: bool = initial_draws > 0 and draws > initial_draws and a.player.visual_shift.x > 0.0 and a.player.position.x == 430.0
	print("BATTLE SHADOW CHECK: %s draws=%d -> %d shift=%s pos=%s" % ["PASS" if ok else "FAIL",initial_draws,draws,str(a.player.visual_shift),str(a.player.position)])
	quit(0 if ok else 1)
