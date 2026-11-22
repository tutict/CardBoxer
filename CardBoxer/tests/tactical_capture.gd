extends SceneTree
## GPU-rendered deterministic UX/combat fixtures, not an alternate game path.
const Arena = preload("res://scripts/arena.gd")
const Defs = preload("res://scripts/tactical_defs.gd")
var a
var output := ""
var captures: Array = []

func resize_window(dimensions: Vector2i) -> void:
	DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED)
	DisplayServer.window_set_size(dimensions)
	await process_frame
	await process_frame

func _initialize() -> void:
	call_deferred("run")

func save_frame(name: String) -> void:
	a.force_redraw()
	a.hud.queue_redraw()
	await process_frame
	await RenderingServer.frame_post_draw
	var shot := root.get_texture().get_image()
	shot.save_png(output+"/"+name+".png")
	var detail: Dictionary = a.hud.tooltip_detail()
	captures.append({"name":name,"width":shot.get_width(),"height":shot.get_height(),"window":str(DisplayServer.window_get_size()),"phase":a.tactical.phase,"hand":a.tactical.hand.size(),"review":a.hud.review_open,"tooltip_height":a.hud._tooltip_height(detail) if not detail.is_empty() else 0})
	print("UI SHOT: %s %dx%d" % [name,shot.get_width(),shot.get_height()])

func fixture_hands(p: Array,e: Array) -> void:
	a.tactical.hand = p.duplicate()
	a.tactical.enemy_hand = e.duplicate()
	for role in ["player","foe"]:
		var cards: Array = p if role == "player" else e
		var remaining: Array = Defs.deck()
		for id in cards:
			remaining.erase(id)
		a.tactical._decks[role] = remaining
		a.tactical._discards[role] = []
	a._mirror_tactical()

func mouse_at(at: Vector2,pressed: bool) -> void:
	var event := InputEventMouseButton.new()
	event.button_index = MOUSE_BUTTON_LEFT
	event.position = at
	event.pressed = pressed
	a._unhandled_input(event)

func forecast_ready() -> void:
	a.tactical.request_forecast()
	var deadline := Time.get_ticks_msec()+3000
	while a.tactical.forecast_status=="pending" and Time.get_ticks_msec()<deadline:
		a.tactical.request_forecast()
		await process_frame

func contact_time(kind: String) -> float:
	for entry in a.tactical._schedule:
		if entry.kind=="contact":
			for hit in entry.group.hits:
				if hit.kind==kind:
					return float(entry.at)
	return -1.0

func feedback_fixture(player_first: String,foe_first: String,distance: int = 1) -> void:
	a.tactical.restart(2026)
	for index in [0,1,2]:
		a.tactical.toggle(index)
	a.tactical.confirm()
	a._process(1.1)
	var player_plan := [player_first,"focus","recover","backstep","guard"]
	var foe_plan := [foe_first,"focus","recover","backstep","guard"]
	fixture_hands(player_plan+["jab","sweep","parry"],foe_plan+["cross","wave","rush"])
	a.tactical.state.distance = distance
	a.tactical.state.player.jokers = []
	a.tactical.state.foe.jokers = []
	a.tactical._enemy_indices = [0,1,2,3,4]
	a.tactical._enemy_plan = foe_plan
	a.tactical.enemy_preview = [foe_first,null,"recover",null,"guard"]
	for index in [0,1,2,3,4]:
		a.tactical.toggle(index)
	a.tactical.confirm()
	a._process(1.1)
	a.hud.hover_kind = ""

func run() -> void:
	output = OS.get_environment("CARD_BOXER_TACTICAL_CAPTURE")
	if output == "":
		push_error("Set CARD_BOXER_TACTICAL_CAPTURE to a writable output folder")
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(output)
	a = Arena.new()
	root.add_child(a)
	if a.player == null:
		a._ready()
	a.set_process(false)
	a.hud.set_process(false)
	await resize_window(Vector2i(1600,900))
	await save_frame("01-loadout")
	for index in [2,0,1]:
		a.tactical.toggle(index)
	await save_frame("02-draft-order")
	a.tactical.confirm()
	a._process(1.1)
	await save_frame("03-eight-hand")
	var p := ["sidestep","jab","backstep","guard","focus","guard_break","armored_heavy","pursuit"]
	var e := ["uppercut","cross","guard","jab","focus","wave","throw","rush"]
	fixture_hands(p,e)
	a.tactical.state.distance = 0
	a.tactical.state.player.jokers = ["shadow","opening","wind"]
	a.tactical.state.foe.jokers = ["counter","pressure","sequence"]
	a.tactical._enemy_indices = [0,1,2,4,7]
	a.tactical._enemy_plan = ["uppercut","cross","guard","focus","rush"]
	a.tactical.enemy_preview = ["uppercut",null,"guard",null,"rush"]
	await save_frame("04-read-and-plan")
	fixture_hands(p+["wave","feint"],e)
	await save_frame("05-ten-hand")
	for index in [0,1,2,3,4]:
		a.tactical.toggle(index)
	await forecast_ready()
	await save_frame("05a-ten-card-plan")
	a.paused = true
	a.tactical.paused = true
	await save_frame("05b-paused-ten-card-plan")
	a.paused = false
	a.tactical.paused = false
	a.tactical.selected.clear()
	fixture_hands(p,e)
	for index in [0,1,2,3,4]:
		a.tactical.toggle(index)
	await forecast_ready()
	await save_frame("06-ordered-plan")
	a.tactical.forecast_status = "pending"
	await save_frame("06e-pending-forecast")
	a.tactical.forecast_status = "error"
	await save_frame("06f-unavailable-forecast")
	a.tactical.forecast_status = "ready"
	a.hud.hover_kind = "plan"
	a.hud.hover_role = "foe"
	a.hud.hover_index = 0
	await save_frame("06a-visible-enemy-details")
	a.hud.hover_index = 1
	await save_frame("06b-hidden-enemy-details")
	a.hud.hover_role = "player"
	a.hud.hover_index = 1
	await save_frame("06c-recovery-and-forecast")
	a.hud.hover_kind = ""
	var from: Vector2 = a.hud.plan_rect("player",0).get_center()
	var to: Vector2 = a.hud.plan_rect("player",4).get_center()
	mouse_at(from,true)
	var motion := InputEventMouseMotion.new()
	motion.position = to
	motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	a._unhandled_input(motion)
	mouse_at(to,false)
	await forecast_ready()
	await save_frame("06d-drag-reordered-plan")
	a.tactical.move_selected(4,0)
	await forecast_ready()
	a.tactical.confirm()
	a._process(0.3)
	await save_frame("07-reveal")
	a._process(0.8)
	var dodge_at := contact_time("dodged")
	a._process(maxf(0.0,dodge_at-a.tactical.resolution_time))
	await save_frame("08-dodge")
	var punish_at := contact_time("punish")
	a._process(maxf(0.0,punish_at-a.tactical.resolution_time))
	await save_frame("09-riposte")
	a._process(12.0)
	await save_frame("10-next-hand")
	a.hud.toggle_review()
	await save_frame("10a-previous-exchange-review")
	a.hud.close_review()
	print("TACTICAL CAPTURE: hp=%d/%d hand=%d native=%s" % [a.player.hp,a.enemy.hp,a.hand.size(),str(a._native_active())])
	feedback_fixture("throw","guard")
	a._process(contact_time("whiff"))
	await save_frame("11-range-miss-reason")
	feedback_fixture("uppercut","jab")
	a._process(contact_time("counter"))
	await save_frame("12-interrupted-startup-reason")
	a.hud.hover_kind = "plan"
	a.hud.hover_role = "player"
	a.hud.hover_index = 0
	await save_frame("12a-player-tooltip-enemy-feedback")
	a.hud.hover_role = "foe"
	await save_frame("12b-enemy-tooltip-player-feedback")
	a.hud.hover_kind = ""
	a._process(100.0)
	await save_frame("13-last-exchange-recap")
	a.tactical.state.player.jokers = ["shadow","opening","wind"]
	a.tactical.state.foe.jokers = ["counter","pressure","sequence"]
	a.hud.toggle_review()
	await save_frame("13a-interruption-review")
	a.hud.close_review()
	feedback_fixture("sidestep","delayed_heavy")
	a._process(contact_time("hit"))
	await save_frame("14-expired-dodge-reason")
	a._process(100.0)
	a.hud.toggle_review()
	await save_frame("14a-expired-dodge-review")
	a.hud.close_review()
	feedback_fixture("guard","throw",0)
	a._process(contact_time("hit"))
	await save_frame("15-bypassed-guard-reason")
	a._process(100.0)
	a.hud.toggle_review()
	await save_frame("15a-bypassed-guard-review")
	a.hud.close_review()
	feedback_fixture("throw","guard")
	a._process(100.0)
	a.hud.toggle_review()
	await save_frame("16-range-miss-review")
	a.hud.close_review()
	print("TACTICAL FEEDBACK CAPTURE: range/interruption/recap/expiry/bypass rendered")
	a._start_tactical_match()
	for index in [2,0,1]:
		a.tactical.toggle(index)
	a.tactical.confirm()
	a._process(1.1)
	fixture_hands(p+["wave","feint"],e)
	a.tactical._enemy_plan = ["uppercut","cross","guard","focus","rush"]
	a.tactical.enemy_preview = ["uppercut",null,"guard",null,"rush"]
	for index in [0,1,2,3,4]:
		a.tactical.toggle(index)
	await forecast_ready()
	var dimensions := [Vector2i(1280,720),Vector2i(1600,900),Vector2i(1920,1080),Vector2i(2560,1440),Vector2i(1600,1000)]
	for viewport_size in dimensions:
		await resize_window(viewport_size)
		await save_frame("viewport-%dx%d-ten-plan" % [viewport_size.x,viewport_size.y])
	feedback_fixture("uppercut","jab")
	a._process(100.0)
	a.tactical.state.player.jokers = ["shadow","opening","wind"]
	a.tactical.state.foe.jokers = ["counter","pressure","sequence"]
	a.hud.toggle_review()
	for viewport_size in dimensions:
		await resize_window(viewport_size)
		await save_frame("viewport-%dx%d-review" % [viewport_size.x,viewport_size.y])
	a.hud.close_review()
	a.tactical._set_phase("match_over","你赢了")
	a.tactical.wins = [2,1]
	await save_frame("17-match-over")
	var manifest := FileAccess.open(output+"/manifest.json",FileAccess.WRITE)
	manifest.store_string(JSON.stringify({"native":a._native_active(),"captures":captures},"\t"))
	a.free()
	quit(0)
