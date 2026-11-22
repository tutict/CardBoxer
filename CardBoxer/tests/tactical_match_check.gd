extends SceneTree
## Deck conservation, fair commitment, exactly-once contacts and bounded matches.
const Defs = preload("res://scripts/tactical_defs.gd")
var match_script
var ai
var failures: Array[String] = []
var checks := 0

func _initialize() -> void:
	if not ResourceLoader.exists("res://scripts/tactical_match.gd") or not ResourceLoader.exists("res://scripts/tactical_ai.gd"):
		expect(false,"tactical match/AI are not implemented")
		finish()
		return
	match_script = load("res://scripts/tactical_match.gd")
	ai = load("res://scripts/tactical_ai.gd")
	if not match_script.can_instantiate() or not ai.can_instantiate():
		expect(false,"match and AI must compile")
		finish()
		return
	check_draft_and_seed()
	check_deck_and_commit()
	check_contact_and_pause()
	check_bonus_hand()
	check_draw_match_limit()
	check_bot_frame_rates()
	finish()

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures.append(label)

func finish() -> void:
	for failure in failures:
		print("FAIL: ",failure)
	print("TACTICAL MATCH CHECK: %d/%d passed" % [checks-failures.size(),checks])
	quit(0 if failures.is_empty() else 1)

func new_match(seed_value: int = 41):
	return match_script.new(seed_value)

func start_round(m) -> void:
	for index in [2,0,1]:
		m.toggle(index)
	m.confirm()
	m.tick(1.1)

func enter_select(m) -> void:
	if m.phase == "intro":
		m.tick(1.1)
	if m.phase == "discard":
		m.confirm()

func check_conservation(m, label: String) -> void:
	for role in ["player","foe"]:
		var cards: Array = m.deck_cards(role)
		expect(cards.size() == 36,label+" physical count "+role)
		for id in Defs.card_ids():
			expect(cards.count(id) == 2,label+" two copies "+role+"/"+id)

func check_draft_and_seed() -> void:
	var m = new_match()
	var other = new_match()
	expect(m.phase == "loadout" and m.offers == other.offers,"seed reproduces six-card draft")
	var unique := {}
	for id in m.offers:
		unique[id] = true
	expect(m.offers.size() == 6 and unique.size() == 6,"draft has six distinct Jokers")
	m.toggle(2)
	m.toggle(0)
	m.toggle(1)
	expect(m.selected == [2,0,1],"draft retains chosen trigger order")
	expect(not m.toggle(3) and m.selected.size() == 3,"draft cannot exceed three")
	m.undo()
	expect(m.selected == [2,0],"undo removes last selected Joker")
	m.toggle(1)
	var equipped: Array = [m.offers[2],m.offers[0],m.offers[1]]
	m.confirm()
	expect(m.state.player.jokers == equipped,"confirm equips in order")
	expect(m.state.foe.jokers.size() == 3,"enemy equips three from its own offer")
	for id in m.state.foe.jokers:
		expect(m.enemy_offers.has(id),"enemy follows its offer restrictions")
	m.tick(1.1)
	start_round(other)
	expect(m.hand == other.hand and m.enemy_hand == other.enemy_hand,"seed reproduces physical opening hands")
	expect(m.hand.size() == 8 and m.enemy_hand.size() == 8,"both opening hands have eight")
	var attacks := 0
	var guards := 0
	for id in m.hand:
		attacks += 1 if Defs.card(id).attack else 0
		guards += 1 if Defs.card(id).kind == "guard" else 0
	expect(attacks >= 2 and guards >= 1,"opening has two attacks and a defence")
	check_conservation(m,"opening")

func check_deck_and_commit() -> void:
	var m = new_match(67)
	start_round(m)
	for index in [0,1,2]:
		m.swap_card(index)
	expect(not m.swap_card(3),"optional swap bound remains three with expanded hand")
	expect(m.phase == "select" and m.enemy_hint != "","enemy commits before player selects")
	var locked: Array = m._enemy_plan.duplicate()
	var public_before: Dictionary = m.public_context("foe")
	var candidate: Array = ai.choose_plan(m.enemy_hand,public_before,"foe")
	m.toggle(0)
	m.toggle(1)
	m.toggle(2)
	m.undo()
	m.toggle(3)
	m.toggle(4)
	m.toggle(5)
	expect(m._enemy_plan == locked,"player edits do not alter committed enemy plan")
	expect(m.enemy_preview.size() == 5 and m.enemy_preview.count(null) == 2,"preview shows actual cards with exactly two masks")
	expect(m.public_context("foe") == public_before,"pending player choice is absent from AI context")
	expect(not public_before.has("hand") and not public_before.has("selected") and not public_before.has("player_plan"),"AI interface excludes hidden input")
	expect(ai.choose_plan(m.enemy_hand,m.public_context("foe"),"foe") == candidate,"AI choice independent of pending player edits")
	check_conservation(m,"after swaps")
	var selection: Array = m.selected.duplicate()
	var chosen: Array = []
	for index in selection:
		chosen.append(m.hand[index])
	m.confirm()
	expect(m.player_plan == chosen,"selected slot order becomes actual action order")
	expect(m.phase == "reveal" and m.state.player.hp == 100 and m.state.foe.hp == 100,"reveal spends cards without applying damage")
	check_conservation(m,"after commitment")

func check_contact_and_pause() -> void:
	var m = new_match(91)
	start_round(m)
	enter_select(m)
	for index in [0,1,2,3,4]:
		m.toggle(index)
	var delivered: Array = []
	m.contact_group.connect(func(group: Dictionary): delivered.append(group.event_id))
	m.confirm()
	m.tick(1.1)
	expect(m.phase == "resolve" and delivered.is_empty(),"resolve begins before first contact")
	var before: Dictionary = m.state.duplicate(true)
	var clock: float = m.resolution_time
	m.paused = true
	m.tick(5.0)
	expect(m.state == before and m.resolution_time == clock and delivered.is_empty(),"pause freezes state and contacts")
	m.paused = false
	m.tick(100.0)
	expect(m.state.player.hp == m.result.next_state.player.hp and m.state.foe.hp == m.result.next_state.foe.hp,"large delta applies every contact exactly once")
	var unique := {}
	for id in delivered:
		unique[id] = true
	expect(unique.size() == delivered.size(),"contact identifiers never repeat")
	var count := delivered.size()
	m.tick(0.01)
	expect(delivered.size() == count,"finished resolution never replays old contacts")
	check_conservation(m,"after resolution")
	m.restart(91)
	expect(m.phase == "loadout" and m.selected.is_empty() and m.state.player.hp == 100,"restart returns to clean draft")
	expect(m.resolution_time == 0.0 and m.result.is_empty(),"restart clears prior resolution")

func check_bonus_hand() -> void:
	var m = new_match(33)
	start_round(m)
	enter_select(m)
	# Controlled five-card scenario; deck invariants use separate fixtures.
	m.state.distance = 0
	m.state.player.jokers = ["shadow","opening","wind"]
	m.hand = ["sidestep","jab","backstep","guard","focus","cross","wave","throw"]
	m.enemy_hand = ["uppercut","cross","guard","jab","focus","wave","throw","rush"]
	m._enemy_indices = [0,1,2,4,7]
	m._enemy_plan = ["uppercut","cross","guard","focus","rush"]
	for index in [0,1,2,3,4]:
		m.toggle(index)
	m.confirm()
	m.tick(1.1)
	m.tick(100.0)
	expect(m.phase == "select" and m.hand.size() == 9,"wind grants nine-card next hand directly in planning")
	expect(m.state.player.extra_draw == 0,"bonus is consumed by one refill")
	expect(m.state.foe.exposed == false,"opening from previous early beat expires")
	var ten_hand: Array = ["jab","jab","cross","uppercut","guard","sidestep","wave","throw","focus","pursuit"]
	var plan: Array = ai.choose_plan(ten_hand,m.public_context("player"),"player")
	var unique := {}
	for index in plan:
		unique[index] = true
	expect(plan.size() == 5 and unique.size() == 5,"AI uses five distinct slots with ten cards")
	expect(ai.choose_discards(ten_hand,m.public_context("player"),"player").size() <= 3,"ten-card discard stays within bound")

func check_draw_match_limit() -> void:
	var m = new_match(29)
	start_round(m)
	var played := 0
	while m.phase != "match_over" and played < 25:
		enter_select(m)
		if m.phase == "round_over":
			m.tick(2.0)
			continue
		if m.phase != "select":
			m.tick(1.1)
			continue
		m.hand = ["guard","focus","recover","backstep","parry","jab","cross","wave"]
		m.enemy_hand = m.hand.duplicate()
		m._enemy_indices = [0,1,2,3,4]
		m._enemy_plan = ["guard","focus","recover","backstep","parry"]
		for index in [0,1,2,3,4]:
			m.toggle(index)
		m.confirm()
		m.tick(1.1)
		m.tick(100.0)
		played += 1
	expect(played == 18 and m.round_index == 3,"six exchanges per round, three rounds even if all draws")
	expect(m.phase == "match_over" and m.match_winner == "draw","all draws terminate as match draw")

func run_bot(seed_value: int, delta: float) -> Dictionary:
	var m = new_match(seed_value)
	m.bot = true
	var ticks := 0
	while m.phase != "match_over" and ticks < int(240.0/delta):
		m.tick(delta)
		ticks += 1
	expect(m.phase == "match_over","bot finishes bounded match at delta "+str(delta))
	check_conservation(m,"bot final")
	return {"wins":m.wins.duplicate(),"hp":[m.state.player.hp,m.state.foe.hp],"winner":m.match_winner,"rounds":m.round_index}

func check_bot_frame_rates() -> void:
	var at30 := run_bot(503,1.0/30.0)
	var at60 := run_bot(503,1.0/60.0)
	var at120 := run_bot(503,1.0/120.0)
	expect(at30 == at60 and at60 == at120,"same seed has same match result at 30, 60 and 120 FPS")
