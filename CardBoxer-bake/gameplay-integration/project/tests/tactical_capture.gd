extends SceneTree
## GPU-rendered deterministic UX/combat fixtures, not an alternate game path.
const Arena = preload("res://scripts/arena.gd")
const Defs = preload("res://scripts/tactical_defs.gd")
var a
var output := ""

func _initialize() -> void:
	call_deferred("run")

func save_frame(name: String) -> void:
	a.force_redraw()
	a.hud.queue_redraw()
	await process_frame
	await RenderingServer.frame_post_draw
	var shot := root.get_texture().get_image()
	shot.save_png(output+"/"+name+".png")

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
	a.tactical.state.player.jokers = ["shadow","opening","wind"]
	a.tactical.state.foe.jokers = ["counter","pressure","sequence"]
	a.tactical._enemy_indices = [0,1,2,4,7]
	a.tactical._enemy_plan = ["uppercut","cross","guard","focus","rush"]
	a.tactical.enemy_preview = ["uppercut",null,"guard",null,"rush"]
	await save_frame("04-read-and-plan")
	fixture_hands(p+["wave","feint"],e)
	await save_frame("05-ten-hand")
	fixture_hands(p,e)
	for index in [0,1,2,3,4]:
		a.tactical.toggle(index)
	await save_frame("06-ordered-plan")
	a.hud.hover_kind = "plan"
	a.hud.hover_role = "foe"
	a.hud.hover_index = 0
	await save_frame("06a-visible-enemy-details")
	a.hud.hover_index = 1
	await save_frame("06b-hidden-enemy-details")
	a.hud.hover_kind = ""
	a.tactical.confirm()
	a._process(0.3)
	await save_frame("07-reveal")
	a._process(0.8)
	a._process(0.56)
	await save_frame("08-dodge")
	a._process(0.94)
	await save_frame("09-riposte")
	a._process(12.0)
	await save_frame("10-next-hand")
	print("TACTICAL CAPTURE: hp=%d/%d hand=%d native=%s" % [a.player.hp,a.enemy.hp,a.hand.size(),str(a._native_active())])
	a.free()
	quit(0)
