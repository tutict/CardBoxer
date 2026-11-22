extends SceneTree
const ArenaScript = preload("res://scripts/arena.gd")
const Rules = preload("res://scripts/taikou_rules.gd")
var failures: Array[String] = []
var total := 0

func expect(ok: bool,label: String) -> void:
	total += 1
	if not ok: failures.append(label)

func _initialize() -> void:
	OS.set_environment("CARD_BOXER_3D","1")
	OS.set_environment("CARD_BOXER_BATTLE_MODE","taikou")
	call_deferred("_run")

func _run() -> void:
	var a = ArenaScript.new()
	root.add_child(a)
	a.set_process(false)
	a.battle_mode = "taikou"
	expect(a._native_active(),"real native layers active")
	if a._native_active():
		expect(a.layer_3d.has_method("anchor_offset") and a.layer_3d_foe.has_method("anchor_offset"),"native layer supplies pure projected anchors")
		if a.layer_3d.has_method("anchor_offset") and a.layer_3d_foe.has_method("anchor_offset"):
			for winner: String in ["player","foe"]:
				for fixture: Array in [[6,7,9],[6,7,8],[8,8,8]]:
					check_contact(a,winner,fixture)
		check_calibrated_shift(a)
	for failure in failures: print("FAIL: ",failure)
	print("BATTLE CONTACT SPACING CHECK: %d/%d passed" % [total-failures.size(),total])
	quit(0 if failures.is_empty() else 1)

func check_calibrated_shift(a) -> void:
	a._start_round()
	a.round_phase = "fight"
	a.presentation.begin_exchange({"round_id":a._round_serial,"winner":"player","actor":"player","target":"foe","clip_id":"jab","action_seq":1,"approach_extra_x":280.0})
	a._advance_presentation(0.48)
	a._sync_3d_layer()
	expect(is_equal_approx(a.last_visuals.player.canvas_shift.x,382.1428571429),"controller adds calibrated lunge to existing contact pulse")
	expect(a.last_visuals.player.frame == 6.0,"calibrated dash does not change authored hand contact frame")

func check_contact(a,winner: String,fixture: Array) -> void:
	a._start_round()
	a.round_phase = "fight"
	a._sync_3d_layer()
	var player_start: Vector2 = a.player.position
	var foe_start: Vector2 = a.enemy.position
	expect(player_start.x == 430.0 and foe_start.x == 850.0,"normal logical spawn preserved")
	expect(a.last_visuals.player.canvas_shift == Vector2.ZERO and a.last_visuals.foe.canvas_shift == Vector2.ZERO,"normal idle has no preapproach shift")
	a.tk_player_result = Rules.evaluate(fixture if winner == "player" else [1,2,4])
	a.tk_enemy_result = Rules.evaluate(fixture if winner == "foe" else [1,2,4])
	a._resolve_taikou()
	var actor = a.player if winner == "player" else a.enemy
	var target = a.enemy if winner == "player" else a.player
	var actor_layer = a.layer_3d if winner == "player" else a.layer_3d_foe
	var target_layer = a.layer_3d_foe if winner == "player" else a.layer_3d
	var clip: String = a.tk_motion_id
	var hand := "rear_hand" if clip == "cross" else ("palms" if clip == "wave" else "lead_hand")
	a._advance_presentation(0.48)
	a._sync_3d_layer()
	var attacker: Dictionary = a.last_visuals[winner]
	var defender: Dictionary = a.last_visuals["foe" if winner == "player" else "player"]
	var fist: Vector2 = actor.position+attacker.canvas_shift+actor_layer.anchor_offset(attacker.pose,hand,attacker.facing,attacker.canvas_tilt)
	var head: Vector2 = target.position+defender.canvas_shift+target_layer.anchor_offset(defender.pose,"head",defender.facing,defender.canvas_tilt)
	var chest: Vector2 = target.position+defender.canvas_shift+target_layer.anchor_offset(defender.pose,"chest",defender.facing,defender.canvas_tilt)
	var weight := clampf((fist.y-head.y)/(chest.y-head.y),0.0,1.0) if absf(chest.y-head.y)>0.0001 else 0.5
	var body: Vector2 = head.lerp(chest,weight)
	print("CONTACT %s/%s hand=%s gap=%.3f positions=%s/%s shifts=%s/%s" % [winner,clip,hand,absf(fist.x-body.x),str(actor.position),str(target.position),str(attacker.canvas_shift),str(defender.canvas_shift)])
	expect(absf(fist.x-body.x)<20.0,"%s/%s normal-spawn fist reaches presented body" % [winner,clip])
	expect(a.player.position == player_start and a.enemy.position == foe_start,"%s/%s lunge never moves gameplay positions" % [winner,clip])
	expect(attacker.frame == a.native_library.contact_frame(winner,clip) and attacker.frozen,"%s/%s keeps exact authored contact and hold" % [winner,clip])
	var spark_found := false
	for effect: Dictionary in a.effects:
		if effect.kind == "spark":
			spark_found = true
			expect((effect.pos as Vector2).distance_to(body)<0.0001,"%s/%s spark shares presented body contact anchor" % [winner,clip])
			break
	expect(spark_found,"%s/%s deferred contact spark exists" % [winner,clip])
	expect(a.has_method("_rhythm_contact_point"),"rhythm spark has a shared native contact anchor")
	if a.has_method("_rhythm_contact_point"):
		expect(a._rhythm_contact_point().distance_to(body)<0.0001,"%s/%s rhythm spark shares hand/body contact anchor" % [winner,clip])
	var held: Vector2 = attacker.canvas_shift
	a._advance_presentation(0.12)
	a._sync_3d_layer()
	expect(a.last_visuals[winner].canvas_shift == held,"%s/%s hitstop freezes calibrated lunge" % [winner,clip])
	a._advance_presentation(0.12)
	a._global_hitstop = 0.0
	a._advance_presentation(1.5)
	a._sync_3d_layer()
	expect(a.last_visuals[winner].canvas_shift == Vector2.ZERO,"%s/%s calibrated lunge returns to logical base" % [winner,clip])
