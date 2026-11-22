extends SceneTree
const FighterScript = preload("res://scripts/fighter.gd")
var failures: Array[String] = []
var total := 0

func expect(ok: bool, label: String) -> void:
	total += 1
	if not ok: failures.append(label)

func _initialize() -> void:
	var fighter = FighterScript.new()
	expect(fighter.has_method("presentation_snapshot"), "Fighter exposes read-only presentation snapshot")
	if fighter.has_method("presentation_snapshot"):
		fighter.reset_for_round(430, 1)
		var before: Dictionary = fighter.presentation_snapshot()
		fighter.play_card("jab")
		var action: Dictionary = fighter.presentation_snapshot()
		expect(action.action_seq == before.action_seq + 1, "new action has unique sequence")
		expect(action.card_id == "jab" and action.phase == "windup", "snapshot retains action clocks")
		fighter.freeze()
		expect(fighter.presentation_snapshot().action_seq == action.action_seq, "freeze preserves action identity")
		fighter.reset_for_round(430, 1)
		fighter.tick(0.05, 1.0, true)
		expect(fighter.presentation_snapshot().walk_phase > 0.0, "walk phase follows traveled distance")
		fighter.position.x = 1130
		var phase: float = fighter.presentation_snapshot().walk_phase
		fighter.tick(0.05, 1.0, true)
		expect(is_equal_approx(fighter.presentation_snapshot().walk_phase, phase), "wall does not advance walk phase")
		fighter.tick(0.2,1.0,true)
		expect(fighter.presentation_snapshot().walk_blend == 0.0 and not fighter.presentation_snapshot().moving, "wall settles into idle without moving legs")
		fighter.reset_for_round(430, 1)
		expect(fighter.presentation_snapshot().walk_blend == 0.0 and fighter.presentation_snapshot().local_hitstop == 0.0, "reset removes walk and hitstop")
	fighter.free()
	expect(ResourceLoader.exists("res://scripts/battle_presentation.gd"), "native battle controller exists")
	if ResourceLoader.exists("res://scripts/battle_presentation.gd") and ResourceLoader.exists("res://scripts/native_motion.gd"):
		check_controller()
	for failure in failures: print("FAIL: ", failure)
	print("BATTLE PRESENTATION CHECK: %d/%d passed" % [total - failures.size(), total])
	quit(0 if failures.is_empty() else 1)

func check_controller() -> void:
	var library = load("res://scripts/native_motion.gd").new()
	expect(library.load_data(), "native data loads")
	if not library.available(): return
	var controller = load("res://scripts/battle_presentation.gd").new()
	controller.setup(library)
	var cues: Array = []
	controller.cue_ready.connect(func(cue: Dictionary): cues.append(cue))
	var snapshot := {"state":0,"card_id":"","action_seq":1,"facing":1,"hp":100}
	var context := {"mode":"taikou","pause":false,"global_hitstop":0.0}
	for crossing in [0.479, 0.480, 0.481]:
		controller.reset(1)
		cues.clear()
		controller.begin_exchange({"round_id":1,"winner":"player","actor":"player","target":"foe","clip_id":"jab","action_seq":1,"impacts":[{"round_id":1,"actor":"player","target":"foe","action_seq":1,"damage":4,"stun_duration":0.26}]})
		controller.advance(crossing, context)
		var visual: Dictionary = controller.sample("player", snapshot, context)
		expect(cues.size() == (0 if crossing < 0.48 else 1), "contact cue boundary %.3f" % crossing)
		if crossing >= 0.48:
			expect(is_equal_approx(visual.frame, 6.0) and visual.frozen, "contact clamps exact jab peak %.3f" % crossing)
			controller.advance(0.1, context)
			expect(cues.size() == 1, "contact cue is emitted once")
	for fps in [30, 60, 120]:
		controller.reset(2)
		cues.clear()
		controller.begin_exchange({"round_id":2,"winner":"player","actor":"player","target":"foe","clip_id":"jab","action_seq":1,"impacts":[{"round_id":2,"actor":"player","target":"foe","action_seq":1,"damage":4,"stun_duration":0.26}]})
		for step in range(ceil(0.48 * fps)):
			controller.advance(1.0 / fps, context)
		expect(cues.size() == 1, "%d fps crossing emits once" % fps)
		expect(is_equal_approx(controller.sample("player", snapshot, context).frame, 6.0), "%d fps crossing stops at contact" % fps)
	controller.reset(3)
	controller.begin_exchange({"round_id":3,"winner":"draw","impacts":[{"round_id":3,"actor":"foe","target":"player","action_seq":1,"stun_duration":0.26},{"round_id":3,"actor":"player","target":"foe","action_seq":1,"stun_duration":0.26}]})
	expect(controller.sample("player", snapshot, context).clip_id == "hit_light", "draw begins both light reactions immediately")
	controller.reset(4)
	controller.begin_exchange({"round_id":4,"winner":"player","actor":"player","target":"foe","clip_id":"jab","action_seq":1,"terminal":true,"impacts":[{"round_id":4,"actor":"player","target":"foe","action_seq":1,"terminal":true,"stun_duration":0.26}]})
	controller.advance(0.48, context)
	controller.advance(0.24, context)
	controller.advance(0.46, context)
	var down: Dictionary = controller.sample("foe", snapshot, context)
	expect(down.clip_id == "ko" and is_equal_approx(down.frame, 27.0), "terminal KO completes and holds independently")
	controller.reset(5)
	expect(controller.sample("foe", snapshot, context).clip_id == "idle", "new round clears terminal visual")
	var realtime := {"mode":"realtime","pause":false,"global_hitstop":0.0,"snapshots":{"player":snapshot,"foe":{"local_hitstop":0.085}}}
	controller.record_impact({"round_id":5,"actor":"player","target":"foe","action_seq":1,"clip_id":"wave","source_kind":"projectile","stun_duration":0.26,"local_hitstop":0.085})
	var new_action := {"state":1,"card_id":"jab","action_seq":2,"phase":"windup","phase_progress":0.5,"facing":1,"hp":100}
	expect(controller.sample("player", new_action, realtime).clip_id == "jab", "late wave collision cannot restore old attack")
	controller.begin_exchange({"round_id":5,"winner":"player","actor":"player","target":"foe","clip_id":"jab","action_seq":2})
	controller.advance(0.2, context)
	var paused_context: Dictionary = context.duplicate()
	paused_context.pause = true
	controller.advance(1.0, paused_context)
	expect(is_equal_approx(controller.exchange_time, 0.2), "pause freezes presentation clock")
	controller.advance(0.035, context)
	expect(is_equal_approx(controller.exchange_time, 0.235), "presentation uses supplied slowed world delta")
	controller.reset(6)
	var recover := {"state":1,"card_id":"wave","action_seq":3,"phase":"recover","phase_progress":0.0,"facing":1,"hp":100}
	var realtime_clear := {"mode":"realtime","pause":false,"global_hitstop":0.0,"snapshots":{"player":recover,"foe":{"local_hitstop":0.0}}}
	controller.record_impact({"round_id":6,"actor":"player","target":"foe","action_seq":3,"clip_id":"wave","source_kind":"release"})
	expect(is_equal_approx(controller.sample("player",recover,realtime_clear).frame,17.0), "wave release displays final active peak before recovery")
	expect(controller.sample("foe",snapshot,realtime_clear).clip_id == "idle", "wave release does not create victim reaction")
	controller.advance(1.0/60.0,realtime_clear)
	expect(controller.sample("player",recover,realtime_clear).frame >= 18.0, "wave release latch lasts only contact frame without hitstop")
	controller.reset(7)
	var dead := {"state":5,"action_seq":1,"facing":-1,"hp":0,"local_hitstop":0.085}
	var over := {"mode":"realtime","terminal":true,"global_hitstop":0.0,"snapshots":{"player":snapshot,"foe":dead}}
	controller.record_impact({"round_id":7,"actor":"player","target":"foe","action_seq":1,"clip_id":"jab","source_kind":"melee","terminal":true,"local_hitstop":0.085,"stun_duration":0.26})
	controller.advance(0.6,over)
	expect(controller.sample("player",snapshot,over).clip_id == "stance", "fatal realtime winner finishes attack and returns to guard")
	expect(controller.sample("foe",dead,over).clip_id == "ko" and is_equal_approx(controller.sample("foe",dead,over).frame,27.0), "fatal realtime victim finishes KO despite frozen gameplay hitstop")
	controller.reset(8)
	controller.record_impact({"round_id":8,"actor":"foe","target":"player","action_seq":1,"clip_id":"jab","source_kind":"melee","local_hitstop":0.085,"stun_duration":0.26})
	expect(controller.sample("player",new_action,realtime_clear).clip_id == "jab", "new action clears old realtime reaction priority")
	controller.reset(9)
	cues.clear()
	var once := {"round_id":9,"winner":"player","actor":"player","target":"foe","clip_id":"jab","action_seq":9,"impacts":[{"round_id":9,"actor":"player","target":"foe","action_seq":9,"source_kind":"taikou","damage":4,"stun_duration":0.26}]}
	controller.begin_exchange(once)
	controller.advance(0.48,context)
	controller.begin_exchange(once)
	controller.advance(0.48,context)
	expect(cues.size() == 1,"duplicate exchange identity cannot re-emit contact")
	controller.reset(10)
	controller.begin_exchange(once)
	controller.record_impact({"round_id":9,"actor":"player","target":"foe","action_seq":9,"source_kind":"melee","clip_id":"jab","terminal":true})
	expect(controller.exchange.is_empty() and controller.sample("foe",snapshot,context).clip_id == "idle","new round rejects stale exchange and impact events")
	controller.reset(11)
	controller.begin_exchange({"round_id":11,"winner":"player","actor":"player","target":"foe","clip_id":"jab","action_seq":1})
	controller.advance(0.5,context)
	controller.advance(0.25,context)
	controller.advance(0.01,context)
	expect(is_equal_approx(controller.exchange_time,0.52),"contact crossing and hold overshoot preserve remaining visual time")
	controller.reset(12)
	controller.begin_exchange({"round_id":12,"winner":"player","actor":"player","target":"foe","clip_id":"jab","action_seq":1,"approach_extra_x":280.0})
	controller.advance(0.48,context)
	var reached: Dictionary = controller.sample("player",snapshot,context)
	expect(is_equal_approx(reached.canvas_shift.x,382.1428571429),"native approach adds calibrated offset to retained pulse at contact")
	expect(reached.frame == 6.0,"native approach retains exact authored contact frame")
	for role: String in ["player","foe"]:
		controller.reset(13)
		controller.begin_exchange({"round_id":13,"winner":role,"actor":role,"target":"foe" if role == "player" else "player","clip_id":"jab","action_seq":1,"approach_extra_x":280.0 if role == "player" else -280.0})
		controller.advance(0.24,context)
		var dashing: Dictionary = controller.sample(role,snapshot,context).pose
		var authored: Dictionary = library.sample(role,"jab",3.0)
		var legs_changed := false
		for bone: String in ["thigh_f","shin_f","thigh_b","shin_b"]:
			var a: Array = dashing.rotations[bone]
			var b: Array = authored.rotations[bone]
			if absf(Quaternion(a[0],a[1],a[2],a[3]).dot(Quaternion(b[0],b[1],b[2],b[3]))) < 0.999999: legs_changed = true
		expect(legs_changed,role+" long approach animates lower legs during dash")
		expect(dashing.rotations.upperarm_f == authored.rotations.upperarm_f and dashing.rotations.forearm_f == authored.rotations.forearm_f and dashing.root_offset == authored.root_offset,role+" dash never alters authored hands or root")
