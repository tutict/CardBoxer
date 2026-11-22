extends SceneTree
## User-visible five-card planning, fair preview and optional same-page swaps.
const Defs = preload("res://scripts/tactical_defs.gd")
const Match = preload("res://scripts/tactical_match.gd")
const Rules = preload("res://scripts/tactical_rules.gd")
const AI = preload("res://scripts/tactical_ai.gd")
var checks := 0
var failures: Array[String] = []

func _initialize() -> void:
	check_one_plan()
	check_preview()
	check_optional_swaps()
	check_five_patterns_and_beats()
	check_generic_effects()
	for failure in failures:
		print("FAIL: ",failure)
	print("TACTICAL PLANNING CHECK: %d/%d passed" % [checks-failures.size(),checks])
	quit(0 if failures.is_empty() else 1)

func expect(ok: bool,label: String) -> void:
	checks += 1
	if not ok:
		failures.append(label)

func planning(seed_value: int = 67):
	var m = Match.new(seed_value)
	for index in [0,1,2]:
		m.toggle(index)
	m.confirm()
	m.tick(1.1)
	expect(m.phase == "select","draft goes directly to planning without discard confirmation")
	# Keep later assertions runnable against the old flow so RED identifies each gap.
	if m.phase == "discard":
		m.confirm()
	return m

func check_one_plan() -> void:
	var m = planning()
	for index in [4,1,7,0]:
		m.toggle(index)
	var physical: Array = m.hand.duplicate()
	expect(not m.confirm() and m.phase == "select" and m.hand == physical,"four actions cannot start or spend cards")
	if m.phase != "select":
		return
	m.toggle(6)
	expect(m.selected == [4,1,7,0,6],"five different physical slots retain one ordered plan")
	expect(not m.toggle(2),"a sixth action is rejected")
	var chosen: Array = []
	for index in [4,1,7,0,6]:
		chosen.append(m.hand[index])
	expect(m.confirm() and m.player_plan == chosen and m.phase == "reveal","one confirmation starts the five-card exchange")
	expect(m.state.player.hp == 100 and m.state.foe.hp == 100,"commitment reveals cards before applying damage")

func check_preview() -> void:
	var masks := {}
	for seed_value in [41,67,121,212]:
		var m = planning(seed_value)
		var locked: Array = m._enemy_plan.duplicate()
		expect(locked.size() == 5,"enemy locks five actions before player selection")
		var preview = m.get("enemy_preview")
		expect(preview is Array and preview.size() == 5,"planning exposes a five-slot enemy preview")
		if not preview is Array or preview.size() != 5 or locked.size() != 5:
			continue
		expect(preview.count(null) == 2,"exactly two enemy cards are randomly masked")
		var visible := 0
		var hidden_slots: Array = []
		for index in range(5):
			if preview[index] == null:
				hidden_slots.append(index)
			else:
				visible += 1
				expect(preview[index] == locked[index],"visible card is the actual committed action")
		expect(visible == 3,"three actual cards are readable before combat")
		masks[str(hidden_slots)] = true
		var before: Array = preview.duplicate()
		var public_before: Dictionary = m.public_context("foe")
		m.toggle(0)
		m.toggle(3)
		m.undo()
		expect(m._enemy_plan == locked and m.enemy_preview == before,"player edits cannot change enemy commitment or masks")
		expect(m.public_context("foe") == public_before,"enemy AI cannot observe pending player input")
		var repeated = planning(seed_value)
		expect(repeated._enemy_plan == locked and repeated.enemy_preview == before,"seed reproduces both enemy plan and random mask")
	expect(masks.size() > 1,"mask positions vary between seeds")

func check_optional_swaps() -> void:
	var m = planning(91)
	expect(m.has_method("swap_card"),"same-page direct optional swap exists")
	if not m.has_method("swap_card"):
		return
	var locked: Array = m._enemy_plan.duplicate()
	var preview: Array = m.enemy_preview.duplicate()
	for index in [0,1,2]:
		m.toggle(index)
	expect(m.swap_card(1) and m.phase == "select","swapping does not leave planning")
	expect(m.selected == [0,2],"swapping removes only that action from the ordered plan")
	expect(m.swap_card(3) and m.swap_card(4),"three optional swaps are permitted")
	var before: Array = m.hand.duplicate()
	expect(not m.swap_card(5) and m.hand == before,"fourth swap does not mutate the hand")
	expect(m.swaps_used == 3,"optional swap budget is counted per exchange")
	expect(m._enemy_plan == locked and m.enemy_preview == preview,"player swaps cannot reroll enemy plan or masks")
	for role in ["player","foe"]:
		var physical: Array = m.deck_cards(role)
		expect(physical.size() == 36,"swapping conserves physical deck size")
		for id in Defs.card_ids():
			expect(physical.count(id) == 2,"swapping conserves both copies of "+id)
	var indices: Array = AI.choose_plan(m.hand,m.public_context("player"),"player")
	var unique := {}
	for index in indices:
		unique[index] = true
	expect(indices.size() == 5 and unique.size() == 5,"AI chooses five unique hand slots")

func check_five_patterns_and_beats() -> void:
	var fixtures := [
		[["jab","feint","cross","parry","guard"],"two_pair",2,1.10],
		[["jab","jab","feint","cross","parry"],"full_house",4,1.35],
		[["jab","cross","uppercut","sweep","wave"],"straight",4,1.30],
		[["cross","cross","parry","sidestep","guard"],"four",5,1.45],
		[["cross","cross","parry","sidestep","sidestep"],"five",6,1.60],
	]
	for fixture in fixtures:
		var pattern: Dictionary = Defs.evaluate(fixture[0])
		expect(pattern.type == fixture[1] and pattern.flat == fixture[2] and is_equal_approx(float(pattern.mult),fixture[3]),"five-card pattern: "+fixture[1])
	var plan := ["guard","focus","recover","backstep","parry"]
	var r: Dictionary = Rules.resolve_exchange(plan,plan,Rules.default_context())
	expect(not r.has("error") and r.events.size() == 5,"five ordered nonattacks produce five beats")
	var short: Dictionary = Rules.resolve_exchange(plan.slice(0,3),plan,Rules.default_context())
	expect(short.has("error") and short.events.is_empty(),"default resolver rejects incomplete three-action plans")
	var late: Dictionary = Rules.resolve_exchange(["guard","focus","recover","guard","sidestep"],["guard","focus","recover","guard","uppercut"],Rules.default_context())
	expect(not late.has("error") and late.next_state.foe.exposed,"fifth-beat dodge creates next-exchange opening")
	if not late.has("error"):
		var next: Dictionary = late.next_state.duplicate(true)
		next.turn = 2
		var riposte: Dictionary = Rules.resolve_exchange(["cross","guard","recover","guard","focus"],["jab","guard","recover","guard","focus"],next)
		expect(riposte.events[0].groups[0].hits[0].kind == "punish","fifth-beat opening enables next-exchange punish")

func check_generic_effects() -> void:
	expect(ResourceLoader.exists("res://scripts/tactical_effects.gd"),"generic effect executor exists")
	if not ResourceLoader.exists("res://scripts/tactical_effects.gd"):
		return
	var effects = load("res://scripts/tactical_effects.gd")
	if not effects.can_instantiate():
		expect(false,"generic effects compile")
		return
	var ctx: Dictionary = Rules.default_context()
	var custom := {"id":"future_card","on_ready":[{"op":"distance","value":-1},{"op":"add","stat":"extra_draw","value":2}]}
	var shift: int = effects.apply_ready(custom,"player",{},ctx,false)
	expect(shift == -1 and ctx.player.extra_draw == 2,"new card effects execute from data without a card-ID branch")
