extends SceneTree
const ArenaScript = preload("res://scripts/arena.gd")
const Defs = preload("res://scripts/tactical_defs.gd")
const Rules = preload("res://scripts/tactical_rules.gd")
var failures: Array[String] = []
var checks := 0
var a

func _initialize() -> void:
	call_deferred("_run_checks")

func _run_checks() -> void:
	if not ResourceLoader.exists("res://scripts/tactical_hud.gd"):
		expect(false,"expanded tactical HUD is not implemented")
		finish()
		return
	var hud_script = load("res://scripts/tactical_hud.gd")
	if not hud_script.can_instantiate():
		expect(false,"tactical HUD must compile")
		finish()
		return
	OS.set_environment("CARD_BOXER_BATTLE_MODE", "tactical")
	OS.set_environment("CARD_BOXER_3D", "1")
	OS.set_environment("CARD_BOXER_SEED", "619")
	a = ArenaScript.new()
	root.add_child(a)
	if a.player == null:
		a._ready()
	a.set_process(false)
	a.hud.set_process(false)
	if a.hud.font == null:
		a.hud._ready()
	expect(a.hud.has_method("handle_click"),"Arena routes tactical play to the new HUD")
	check_offers_and_mouse()
	check_ten_hand_and_keyboard()
	check_plans_and_swaps()
	check_compact_faces()
	check_exact_timing_and_drag()
	check_range_faces()
	check_feedback_faces()
	check_pause_and_redraw()
	a.free()
	finish()

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures.append(label)

func check_range_faces() -> void:
	var m = a.tactical
	var h = a.hud
	m.phase = "select"
	m.selected = [0]
	m.hand = ["throw","uppercut","sweep","wave","cross","guard","sidestep","feint","rush","recover"]
	for fixture in [[0,"贴身"],[1,"贴身"],[2,"中距"],[3,"中距–远距"],[4,"贴身–中距"]]:
		var face: Dictionary = h.hand_face(fixture[0])
		expect(face.get("range","")==fixture[1],"hand shows reach before a full plan is selected: "+m.hand[fixture[0]])
		var rect: Rect2 = h.hand_rect(fixture[0])
		var swap: Rect2 = h.swap_card_rect(fixture[0])
		var width: float = h.font.get_string_size(String(face.get("range","")),HORIZONTAL_ALIGNMENT_LEFT,-1,13).x
		expect(rect.position.x+11.0+width<swap.position.x,"reach label stays clear of ten-card swap target")
	expect(h.plan_face("player",0).get("stat","").contains("贴身"),"partial plan face exposes close-only reach")
	m.selected = [0,1,2,3,4]
	m.forecast = {"beats":[{"label":"会被打断","certain":true},{"label":"会被打断","certain":true},{"label":"会被打断","certain":true},{"label":"会被打断","certain":true},{"label":"会被打断","certain":true}]}
	m.forecast_status = "ready"
	for id in ["armored_heavy","delayed_heavy","guard_break","wave","pursuit"]:
		m.hand[0] = id
		var face: Dictionary = h.plan_face("player",0)
		var text: String = face.stat+" · "+face.forecast_label
		expect(h.font.get_string_size(text,HORIZONTAL_ALIGNMENT_LEFT,-1,12).x<=h.plan_rect("player",0).size.x-52.0,"reach and risk fit the compact plan stat line: "+id)

func check_feedback_faces() -> void:
	var m = a.tactical
	var h = a.hud
	m.state = Rules.default_context()
	m.player_plan = ["uppercut","focus","recover","backstep","guard"]
	m.enemy_plan = ["jab","focus","recover","backstep","guard"]
	m.enemy_preview = m.enemy_plan.duplicate()
	m._begin_resolve()
	expect(not h.plan_face("player",0).has("result_label"),"HUD does not expose precomputed interruption before contact")
	m.tick(0.44)
	expect(h.plan_face("player",0).get("result_label","").contains("打断"),"HUD shows actual cancelled startup in its original plan slot")
	expect(not h.plan_face("player",1).has("result_label"),"HUD leaves later action outcomes undisclosed")
	m.phase = "select"
	m.selected = []

func finish() -> void:
	for failure in failures:
		print("FAIL: ",failure)
	print("TACTICAL UI CHECK: %d/%d passed" % [checks-failures.size(),checks])
	quit(0 if failures.is_empty() else 1)

func key(code: int,shift: bool = false) -> void:
	var event := InputEventKey.new()
	event.keycode = code
	event.pressed = true
	event.shift_pressed = shift
	a._unhandled_input(event)

func check_offers_and_mouse() -> void:
	var h = a.hud
	var canvas := Rect2(0,0,1600,900)
	for i in range(6):
		var rect: Rect2 = h.offer_rect(i)
		expect(canvas.encloses(rect),"offer fits logical canvas: "+str(i))
		for j in range(i):
			expect(not rect.intersects(h.offer_rect(j)),"offer click targets do not overlap")
	for i in [2,0,1]:
		h.handle_click(h.offer_rect(i).get_center())
	expect(a.tactical.selected == [2,0,1],"mouse selection retains trigger order")
	h.handle_click(h.offer_rect(0).get_center())
	expect(a.tactical.selected == [2,1],"mouse can cancel a chosen Joker")
	key(KEY_BACKSPACE)
	expect(a.tactical.selected == [2],"keyboard undo is equivalent to cancel")
	for i in [0,1]:
		h.handle_click(h.offer_rect(i).get_center())
	h.handle_click(h.confirm_rect().get_center())
	a._process(1.1)
	expect(a.tactical.phase == "select","mouse draft confirmation starts planning directly")

func check_ten_hand_and_keyboard() -> void:
	var h = a.hud
	var canvas := Rect2(0,0,1600,900)
	for count in [8,9,10]:
		a.tactical.hand = Defs.card_ids().slice(0,count)
		a._mirror_tactical()
		for i in range(count):
			var rect: Rect2 = h.hand_rect(i)
			expect(canvas.encloses(rect),"expanded card fits: %d/%d" % [i,count])
			if i>0:
				expect(not rect.intersects(h.hand_rect(i-1)),"expanded hand has independent hit targets")
	key(KEY_0)
	expect(a.tactical.selected == [9],"zero key selects tenth slot")
	h.handle_click(h.hand_rect(9).get_center())
	expect(a.tactical.selected.is_empty(),"mouse cancels the same tenth slot")
	h.handle_click(Vector2(1450,780))
	expect(a.tactical.selected == [9],"expanded rightmost hand target is usable on the larger page")
	a.tactical.selected.clear()
	for i in [7,4,1,9,2]:
		h.handle_click(h.hand_rect(i).get_center())
	expect(a.tactical.selected == [7,4,1,9,2],"mouse five-card ordering is preserved")
	key(KEY_BACKSPACE)
	expect(a.tactical.selected == [7,4,1,9],"keyboard undoes last mouse-selected card")

func check_plans_and_swaps() -> void:
	var h = a.hud
	expect(h.has_method("plan_rect") and h.has_method("plan_card"),"five-slot plan layout and visible-card access exist")
	expect(h.has_method("swap_card_rect"),"direct optional swap button exists on each card")
	if not h.has_method("plan_rect") or not h.has_method("swap_card_rect"):
		return
	var canvas := Rect2(0,0,1600,900)
	var all_rects: Array = []
	var hidden := 0
	for role in ["player","foe"]:
		for index in range(5):
			var rect: Rect2 = h.plan_rect(role,index)
			expect(canvas.encloses(rect),"five-plan slot fits expanded canvas")
			expect(rect.end.y<=370.0,"compact planning rows leave the actor stage open")
			expect(rect.size.y<=56.0,"planning slots stay compact")
			for other in all_rects:
				expect(not rect.intersects(other),"both plans have independent visible slots")
			all_rects.append(rect)
			if role == "foe":
				var id = h.plan_card(role,index)
				hidden += 1 if id == null else 0
				expect(id == a.tactical.enemy_preview[index],"HUD exposes only the actual enemy preview")
	expect(hidden == 2,"HUD keeps exactly two enemy cards hidden")
	a.tactical.selected.clear()
	for index in [0,1,2]:
		h.handle_click(h.hand_rect(index).get_center())
	h.handle_click(h.plan_rect("player",1).get_center())
	expect(a.tactical.selected == [0,2],"clicking an action slot removes only that planned card")
	h.handle_click(h.swap_card_rect(0).get_center())
	expect(a.tactical.swaps_used == 1 and a.tactical.selected == [2],"mouse swap replaces only that card on the same page")
	key(KEY_4,true)
	expect(a.tactical.swaps_used == 2 and a.tactical.selected == [2],"Shift plus number performs an equivalent optional swap")
	for index in range(10):
		expect(h.hand_rect(index).encloses(h.swap_card_rect(index)),"swap target stays inside its own hand card")

func check_pause_and_redraw() -> void:
	var h = a.hud
	var before: String = h._visual_key()
	key(KEY_1)
	expect(h._visual_key() != before,"selection dirties the tactical redraw signature")
	key(KEY_P)
	var chosen: Array = a.tactical.selected.duplicate()
	h.handle_click(h.hand_rect(2).get_center())
	expect(a.tactical.selected == chosen,"paused mouse click does not change plan")
	key(KEY_P)
	key(KEY_R)
	expect(a.tactical.phase == "loadout" and a.tactical.selected.is_empty(),"restart works from tactical HUD")

func check_compact_faces() -> void:
	var h = a.hud
	expect(h.has_method("hand_face") and h.has_method("plan_face") and h.has_method("card_detail"),"concise faces and full details have separate view models")
	if not h.has_method("hand_face") or not h.has_method("plan_face") or not h.has_method("card_detail"):
		return
	var m = a.tactical
	m.phase = "select"
	m.hand = ["jab","guard","cross","sidestep","wave","focus","recover","backstep"]
	m.selected = [3,0]
	m.enemy_plan = ["uppercut","jab","cross","sidestep","guard"]
	m.enemy_preview = ["uppercut",null,"cross",null,"guard"]
	var hand_face: Dictionary = h.hand_face(0)
	expect(hand_face.name == "刺拳" and hand_face.rank == 1,"hand face keeps action name and rank")
	expect(hand_face.stat == "起手4 · 4伤" and hand_face.step == 2,"hand face shows exact startup and damage with selected order")
	expect(not hand_face.has("text") and not hand_face.has("description"),"full card copy stays off the hand face")
	var open_face: Dictionary = h.plan_face("foe",0)
	var hidden_face: Dictionary = h.plan_face("foe",1)
	var empty_face: Dictionary = h.plan_face("player",4)
	expect(open_face.state == "visible" and open_face.name == "上勾拳" and open_face.stat.begins_with("起手8 · 10伤") and open_face.stat.contains("贴身"),"open enemy slot shows exact startup, damage and reach")
	expect(hidden_face.state == "masked" and not hidden_face.has("name"),"masked enemy slot reveals no action text")
	expect(empty_face.state == "empty" and empty_face.slot == 5,"empty player slot carries only its position")
	var detail: Dictionary = h.card_detail("jab")
	expect(detail.body == Defs.card("jab").text and detail.body != "","full rules text remains available on hover")
	expect(ResourceLoader.exists("res://assets/tactical/hidden_card_back.png"),"hidden enemy slots can use the Comfy-generated card back")

func mouse(at: Vector2,pressed: bool) -> void:
	var event := InputEventMouseButton.new()
	event.button_index = MOUSE_BUTTON_LEFT
	event.position = at
	event.pressed = pressed
	a._unhandled_input(event)

func motion(at: Vector2) -> void:
	var event := InputEventMouseMotion.new()
	event.position = at
	event.button_mask = MOUSE_BUTTON_MASK_LEFT
	a._unhandled_input(event)

func check_exact_timing_and_drag() -> void:
	var h = a.hud
	var m = a.tactical
	m.hand = ["uppercut","guard","cross","sidestep","wave","focus","recover","backstep"]
	m.selected = [0,1,2,3,4]
	var face: Dictionary = h.hand_face(0)
	expect(face.get("windup",-1)==8 and face.get("damage",-1)==10 and face.mark=="终","face separates exact startup, damage and finisher role")
	var detail: Dictionary = h.card_detail("uppercut")
	expect(detail.get("recover",-1)==13 and detail.get("whiff_recover",-1)==19 and detail.get("role","")=="终结","hover exposes real recovery risk and combo role")
	for id in Defs.CARD_IDS:
		expect(h._wrap_pixels(Defs.card(id).text,304,16).size()<=4,"full card description fits the hover body: "+id)
	var forecast_script = load("res://scripts/tactical_forecast.gd")
	m.forecast = forecast_script.forecast_plan(m.selected.map(func(index): return m.hand[index]),m.enemy_preview,m.public_context("player"))
	m.forecast_status = "ready"
	m.forecast_revision += 1
	expect(h.plan_face("player",0).get("forecast_label","")=="距离风险","planning slot displays a real wrong-distance forecast")
	expect(not h.plan_face("foe",1).has("forecast_label"),"masked enemy slot cannot inherit simulated card information")
	var locked: Array = m._enemy_plan.duplicate()
	var preview: Array = m.enemy_preview.duplicate()
	var hand: Array = m.hand.duplicate()
	var from: Vector2 = h.plan_rect("player",0).get_center()
	var to: Vector2 = h.plan_rect("player",3).get_center()
	m.selected = [0,1,2,3,4]
	mouse(from,true)
	expect(m.selected==[0,1,2,3,4],"plan pointer-down waits to distinguish click from drag")
	motion(to)
	mouse(to,false)
	expect(m.selected==[1,2,3,0,4],"native mouse motion and release reorder through Arena")
	expect(m.hand==hand and m._enemy_plan==locked and m.enemy_preview==preview,"drag changes only physical selection order")
	m.selected = [0,1,2,3,4]
	mouse(to,true)
	mouse(to,false)
	expect(m.selected==[0,1,2,4],"ordinary click still withdraws exactly one planned action")
	m.selected = [0,1,2,3,4]
	mouse(from,true)
	motion(Vector2(20,600))
	mouse(Vector2(20,600),false)
	expect(m.selected==[0,1,2,3,4],"outside drop leaves the plan intact")
	m.selected = [0,1,2,3,4]
	mouse(from,true)
	key(KEY_BACKSPACE)
	motion(to)
	mouse(to,false)
	expect(m.selected==[0,1,2,3],"keyboard edit during a drag cancels the stale drag snapshot")
	m.selected = [0,1,2,3,4]
	var last: Vector2 = h.plan_rect("player",4).get_center()
	mouse(last,true)
	key(KEY_BACKSPACE)
	key(KEY_5,true)
	key(KEY_5)
	expect(m.selected==[0,1,2,3,4],"accepted keyboard edits can restore the same physical-slot array")
	motion(to)
	mouse(to,false)
	expect(m.selected==[0,1,2,3,4],"restored slot array cannot revive a drag of an earlier hand card")
	m.selected = [0,1,2,3,4]
	mouse(from,true)
	var live_forecast: Dictionary = forecast_script.forecast_plan(m.selected.map(func(index): return m.hand[index]),m.enemy_preview,m.public_context("player"))
	m._publish_forecast(live_forecast)
	motion(to)
	mouse(to,false)
	expect(m.selected==[1,2,3,0,4],"background forecast publication does not cancel an otherwise valid drag")
