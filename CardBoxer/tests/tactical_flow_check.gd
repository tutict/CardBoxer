extends SceneTree
## Physical reorder and recovery-driven playback through the actual controller.
const Match = preload("res://scripts/tactical_match.gd")
const Rules = preload("res://scripts/tactical_rules.gd")
const Defs = preload("res://scripts/tactical_defs.gd")
const Presenter = preload("res://scripts/tactical_presenter.gd")
var checks := 0
var failures: Array[String] = []

func _initialize() -> void:
	check_reorder()
	check_carry_and_round_reset()
	check_playback_handoff()
	check_defense_contact_pose()
	check_pose_identity()
	for failure in failures:
		print("FAIL: ",failure)
	print("TACTICAL FLOW CHECK: %d/%d passed" % [checks-failures.size(),checks])
	quit(0 if failures.is_empty() else 1)

func expect(ok: bool,label: String) -> void:
	checks += 1
	if not ok:
		failures.append(label)

func planning(seed_value: int = 97):
	var m = Match.new(seed_value)
	for index in [0,1,2]:
		m.toggle(index)
	m.confirm()
	m.tick(1.1)
	return m

func set_hands(m,p: Array,e: Array) -> void:
	m.hand = p.duplicate()
	m.enemy_hand = e.duplicate()
	for role in ["player","foe"]:
		var cards: Array = p if role=="player" else e
		var deck: Array = Defs.deck()
		for id in cards:
			deck.erase(id)
		m._decks[role] = deck
		m._discards[role] = []
		m.state[role].jokers = []
	m._enemy_indices = [0,1,2,3,4]
	m._enemy_plan = e.slice(0,5)
	m.enemy_preview = [e[0],null,e[2],null,e[4]]

func check_reorder() -> void:
	var m = planning()
	for index in [5,1,6,0,4]:
		m.toggle(index)
	expect(m.has_method("move_selected"),"controller supports ordered physical-slot movement")
	if not m.has_method("move_selected"):
		return
	var hand: Array = m.hand.duplicate()
	var locked: Array = m._enemy_plan.duplicate()
	var preview: Array = m.enemy_preview.duplicate()
	var physical: Array = m.deck_cards("player")
	expect(m.move_selected(0,3) and m.selected==[1,6,0,5,4],"drag move inserts one physical slot at its destination")
	expect(m.hand==hand and m.deck_cards("player")==physical and m.swaps_used==0,"reorder neither spends nor swaps cards")
	expect(m._enemy_plan==locked and m.enemy_preview==preview,"reorder cannot change enemy commitment or mask")
	var order: Array = m.selected.duplicate()
	expect(not m.move_selected(-1,2) and not m.move_selected(1,9) and m.selected==order,"invalid move leaves the entire order intact")
	m.paused = true
	expect(not m.move_selected(0,1) and m.selected==order,"paused plans cannot reorder")
	m.paused = false
	var chosen: Array = m.selected.map(func(index): return m.hand[index])
	m.confirm()
	expect(m.player_plan==chosen and not m.move_selected(0,1),"commit consumes the new order and prevents later edits")

func check_carry_and_round_reset() -> void:
	var m = planning(121)
	set_hands(m,["guard","feint","recover","focus","sidestep","jab","cross","wave"],["guard","feint","recover","focus","jab","cross","sweep","wave"])
	for index in [0,1,2,3,4]:
		m.toggle(index)
	m.confirm()
	m.tick(1.1)
	m.tick(100.0)
	expect(m.phase=="select" and m.state.foe.ready_delay==4,"fifth-beat short whiff survives next-round planning")
	expect(not m.state.player.combo.open,"last-beat defense cannot carry a combo")
	var before: Dictionary = m.state.duplicate(true)
	m.tick(0.5)
	expect(m.state==before,"planning does not consume logical recovery")
	for role in ["player","foe"]:
		expect(m.deck_cards(role).size()==36,"carry and refill preserve the physical deck")
	m.round_index += 1
	m._new_round()
	expect(m.state.player.ready_delay==0 and m.state.foe.ready_delay==0,"new round resets carried recovery")
	expect(m.state.player.recovery.is_empty() and m.state.foe.recovery.is_empty(),"new round resets recovery pose metadata")

func check_playback_handoff() -> void:
	var m = Match.new(1)
	m.state = Rules.default_context()
	m.player_plan = ["sidestep","cross","guard","focus","guard"]
	m.enemy_plan = ["jab","guard","focus","guard","focus"]
	var presenter = Presenter.new()
	m.beat_started.connect(presenter.begin_beat)
	m._begin_resolve()
	var second_at := -1.0
	for entry in m._schedule:
		if entry.kind=="beat" and entry.beat.beat==2:
			second_at = float(entry.at)
	# First beat ends after logical frame8, one 0.1 hit hold and a 0.1 gap.
	expect(is_equal_approx(second_at,0.8),"schedule waits common recovery only, not full recovery plus another delay")
	m.tick(second_at+0.01)
	var waiting: Dictionary = presenter.sample(m,"foe")
	expect(waiting.card_id=="jab" and waiting.phase=="recover","waiting opponent continues its previous whiff recovery")
	m.tick(0.5)
	var released: Dictionary = presenter.sample(m,"foe")
	expect(released.card_id=="guard","new action begins after the carried wait")
	var time: float = m.resolution_time
	m.paused = true
	m.tick(10.0)
	expect(m.resolution_time==time and presenter.sample(m,"foe").frozen,"pause freezes carry as well as new startup")

func check_pose_identity() -> void:
	var m = Match.new(1)
	m.state = Rules.default_context()
	m.phase = "resolve"
	m.player_plan = ["guard","guard","guard","guard","guard"]
	m.enemy_plan = m.player_plan.duplicate()
	var result: Dictionary = Rules.resolve_exchange(m.player_plan,m.enemy_plan,m.state)
	var presenter = Presenter.new()
	m.active_beat = result.events[4]
	m.active_beat["pauses"] = []
	m.active_beat["duration"] = 1.0
	presenter.begin_beat(m.active_beat)
	var first: Dictionary = presenter.sample(m,"player")
	m.turn_index = 2
	m.active_beat = result.events[1]
	m.active_beat["pauses"] = []
	m.active_beat["duration"] = 1.0
	presenter.begin_beat(m.active_beat)
	var second: Dictionary = presenter.sample(m,"player")
	expect(first.action_seq!=second.action_seq,"five-beat pose IDs cannot collide across exchanges")

func check_defense_contact_pose() -> void:
	for fixture in [["sidestep","wave",2,0.68,"dodged","dodging"],["parry","uppercut",0,0.60,"parried","guarding"]]:
		var m = Match.new(1)
		m.state = Rules.default_context()
		m.state.distance = fixture[2]
		m.player_plan = [fixture[0],"guard","focus","recover","backstep"]
		m.enemy_plan = [fixture[1],"guard","focus","recover","backstep"]
		var presenter = Presenter.new()
		m.beat_started.connect(presenter.begin_beat)
		m._begin_resolve()
		m.tick(float(fixture[3]))
		expect(m.latest_hits.size()==1 and m.latest_hits[0].kind==fixture[4],"fixture reaches an actual successful defense contact")
		var snapshot: Dictionary = presenter.sample(m,"player")
		expect(snapshot.state==1 and bool(snapshot[fixture[5]]),"active defense pose remains visible when contact follows its recovery-ready time: "+fixture[0])
