extends SceneTree
## Exercises the optimized HUD's public information and protected review input.
const Arena = preload("res://scripts/arena.gd")
const Defs = preload("res://scripts/tactical_defs.gd")
const Rules = preload("res://scripts/tactical_rules.gd")
var a
var checks := 0
var failures: Array[String] = []

func _initialize() -> void:
	call_deferred("run")

func expect(ok: bool,label: String) -> void:
	checks += 1
	if not ok:
		failures.append(label)

func key(code: int,shift: bool = false) -> void:
	var event := InputEventKey.new()
	event.keycode = code
	event.pressed = true
	event.shift_pressed = shift
	a._unhandled_input(event)

func run() -> void:
	OS.set_environment("CARD_BOXER_BATTLE_MODE","tactical")
	OS.set_environment("CARD_BOXER_3D","1")
	OS.set_environment("CARD_BOXER_SEED","619")
	a = Arena.new()
	root.add_child(a)
	a.set_process(false)
	a.hud.set_process(false)
	for index in [2,0,1]:
		a.tactical.toggle(index)
	a.tactical.confirm()
	a._process(1.1)
	check_operation_geometry()
	check_forecast_states()
	check_side_feedback()
	check_review_input()
	a.free()
	for failure in failures:
		print("FAIL: ",failure)
	print("TACTICAL UI OPTIMIZATION CHECK: %d/%d passed" % [checks-failures.size(),checks])
	quit(0 if failures.is_empty() else 1)

func check_operation_geometry() -> void:
	var h = a.hud
	var m = a.tactical
	var canvas := Rect2(0,0,1600,900)
	m.hand = ["jab","delayed_heavy","armored_heavy","guard_break","uppercut","wave","throw","parry","feint","pursuit"]
	for selected in [[],[0,1,2,3,4]]:
		m.selected = selected.duplicate()
		for index in range(10):
			var card: Rect2 = h.hand_rect(index)
			expect(canvas.encloses(card),"ten-card hand remains wholly visible, including selected lift")
			expect(not card.intersects(h.confirm_rect()) and not card.intersects(h.undo_rect()),"selected cards do not cover action buttons")
			expect(card.encloses(h.swap_card_rect(index)),"every swap target belongs to its card")
		for role in ["player","foe"]:
			for index in range(5):
				var rect: Rect2 = h.plan_rect(role,index)
				expect(rect.end.y<=320.0,"both plan rows leave the expanded actor stage visible")
				expect(rect.size.y==54.0,"compact plan slots preserve the approved height")
				expect(rect.position.x==h.plan_rect("foe" if role=="player" else "player",index).position.x,"both sides share the same beat column")
	expect(h.has_method("plan_content_rects") and h.has_method("hand_range_rect"),"readable timing, reach and status have independent layout regions")
	if not h.has_method("plan_content_rects") or not h.has_method("hand_range_rect"):
		return
	for index in range(10):
		expect(not h.hand_range_rect(index).intersects(h.swap_card_rect(index)),"reach markers stay clear of the ten-card swap target")
	m.selected = [0,1,2,3,4]
	m.forecast_status = "pending"
	for id in Defs.CARD_IDS:
		m.hand[0] = id
		var face: Dictionary = h.plan_face("player",0)
		var regions: Dictionary = h.plan_content_rects("player",0)
		expect(h.plan_rect("player",0).encloses(regions.name),"full action title stays in its assigned slot: "+id)
		expect(h.font.get_string_size(face.name,HORIZONTAL_ALIGNMENT_LEFT,-1,20).x<=regions.name.size.x,"long Chinese action names fit beside their status: "+id)
		expect(h.font.get_string_size(face.timing,HORIZONTAL_ALIGNMENT_LEFT,-1,18).x<=regions.timing.size.x,"exact timing remains readable beside reach: "+id)
		expect(not regions.name.intersects(regions.status),"action name and forecast label do not overlap: "+id)
		expect(not regions.timing.intersects(regions.range),"timing and reach do not overlap: "+id)

func check_forecast_states() -> void:
	var h = a.hud
	var m = a.tactical
	m.hand = ["jab","guard","cross","sidestep","wave","focus","recover","backstep"]
	m.selected = [0,1,2,3,4]
	m.enemy_preview = ["uppercut",null,"cross",null,"guard"]
	m.forecast = {"beats":[]}
	for index in range(5):
		m.forecast.beats.append({"label":"结果未定","certain":false,"kinds":["hit","whiff"],"damage_min":0,"damage_max":8,"start_min":4,"start_max":8,"window_min":0,"window_max":12})
	m.forecast_status = "ready"
	var face: Dictionary = h.plan_face("player",0)
	expect(face.has("status_badge"),"prediction is a separate badge rather than part of timing")
	if not face.has("status_badge"):
		return
	expect(face.status_badge.kind=="forecast" and not face.status_badge.certain,"uncertain public forecasts keep their uncertainty")
	expect(String(face.status_badge.text).begins_with("预估"),"predictions identify themselves before combat")
	m.forecast.beats[0].certain = true
	expect(h.plan_face("player",0).status_badge.certain,"consistent outcome classes receive the certain style")
	m.forecast_status = "pending"
	expect(h.plan_face("player",0).status_badge.kind=="pending","pending state replaces stale ready predictions")
	m.forecast_status = "error"
	expect(not h.plan_face("player",0).has("status_badge"),"forecast errors cannot retain an old success or risk label")
	m.forecast_status = "ready"
	m.selected = [0,1,2,3]
	expect(not h.plan_face("player",0).has("status_badge"),"partial plans make no outcome commitment")
	var hidden: Dictionary = h.plan_face("foe",1)
	expect(hidden.keys().size()==2 and hidden.state=="masked","masked cards reveal neither reach, class nor forecast")
	var cells: Array = h.hand_face(0).get("range_cells",[])
	expect(cells==[true,true,false],"jab reach shows close and middle, with far uncovered")
	m.hand[0] = "wave"
	expect(h.hand_face(0).range_cells==[false,true,true],"wave reach shows middle and far without promising a hit")

func check_side_feedback() -> void:
	var h = a.hud
	var m = a.tactical
	m.state = Rules.default_context()
	m.player_plan = ["uppercut","focus","recover","backstep","guard"]
	m.enemy_plan = ["jab","focus","recover","backstep","guard"]
	m.enemy_preview = m.enemy_plan.duplicate()
	m._begin_resolve()
	m.tick(0.44)
	expect(h.has_method("source_feedback"),"each actor owns an independent executed-feedback panel")
	if not h.has_method("source_feedback"):
		return
	h.hover_kind = "plan"
	h.hover_role = "player"
	h.hover_index = 0
	expect(h.source_feedback("player").is_empty(),"player tooltip replaces only the player panel")
	expect(not h.source_feedback("foe").is_empty(),"enemy feedback remains visible while reading the player")
	h.hover_role = "foe"
	expect(not h.source_feedback("player").is_empty() and h.source_feedback("foe").is_empty(),"enemy tooltip leaves player feedback visible")
	h.hover_kind = ""
	expect(not h.source_feedback("player").is_empty() and not h.source_feedback("foe").is_empty(),"both executed panels return after hover ends")
	expect(not h.plan_face("player",1).has("result_label"),"later beats still reveal no precomputed result")
	m.tick(100.0)

func check_review_input() -> void:
	var h = a.hud
	var m = a.tactical
	expect(h.has_method("toggle_review") and m.has_method("last_exchange_details"),"last exchange has a read-only review and deep-copy accessor")
	if not h.has_method("toggle_review") or not m.has_method("last_exchange_details"):
		return
	expect(m.phase=="select" and not m.last_exchange_details().is_empty(),"review fixture has completed an exchange and returned to planning")
	m.selected = [0,1]
	h.focus_card(1)
	var before: String = m.signature()
	var elapsed: float = m.phase_time
	key(KEY_H)
	expect(h.review_open,"H opens a completed exchange review")
	expect(h.review_snapshot.feedback.player.size()==5 and h.review_snapshot.feedback.foe.size()==5,"review contains all five executed beats for both sides")
	var detached: Dictionary = m.last_exchange_details()
	detached.feedback.player[0].label = "changed by consumer"
	expect(m.last_exchange_details().feedback.player[0].label=="被打断","review accessor protects the recorded nested feedback")
	for code in [KEY_3,KEY_0,KEY_BACKSPACE,KEY_SPACE,KEY_ENTER]:
		key(code)
	key(KEY_4,true)
	h.handle_click(h.hand_rect(2).get_center())
	h.handle_click(h.swap_card_rect(0).get_center())
	h.handle_click(h.confirm_rect().get_center())
	var press := InputEventMouseButton.new()
	press.button_index = MOUSE_BUTTON_LEFT
	press.pressed = true
	press.position = h.plan_rect("player",0).get_center()
	a._unhandled_input(press)
	var drag := InputEventMouseMotion.new()
	drag.position = h.plan_rect("player",1).get_center()
	drag.button_mask = MOUSE_BUTTON_MASK_LEFT
	a._unhandled_input(drag)
	press.pressed = false
	press.position = drag.position
	a._unhandled_input(press)
	a._process(1.0)
	expect(m.signature()==before,"review blocks selection, swaps, confirmation and stale drag without mutating the match")
	expect(m.phase_time==elapsed,"review does not advance match time")
	key(KEY_ESCAPE)
	expect(not h.review_open and h.keyboard_focus_index==1,"Esc closes review and restores keyboard detail focus")
	expect(m.selected==[0,1],"closing review preserves the current plan")
	h.handle_click(h.review_rect().get_center())
	expect(h.review_open,"mouse review entry is equivalent to H")
	h.handle_click(h.review_close_rect().get_center())
	expect(not h.review_open,"mouse close is equivalent to Esc")
	h.toggle_review()
	key(KEY_R)
	expect(not h.review_open and h.review_snapshot.is_empty(),"restart immediately clears the open review")
	expect(m.phase=="loadout" and m.last_exchange_details().is_empty(),"restart removes the preceding exchange snapshot")
	key(KEY_H)
	expect(not h.review_open,"no previous snapshot means no review on a new draft")
