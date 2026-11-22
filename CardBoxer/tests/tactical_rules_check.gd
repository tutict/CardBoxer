extends SceneTree
## Deterministic, behavior-level combat scenarios. Run with --headless --script.

var failures: Array[String] = []
var checks := 0
var rules
var defs

func _initialize() -> void:
	if not ResourceLoader.exists("res://scripts/tactical_rules.gd") or not ResourceLoader.exists("res://scripts/tactical_defs.gd"):
		expect(false, "tactical combat/catalog modules are not implemented")
		finish()
		return
	rules = load("res://scripts/tactical_rules.gd")
	defs = load("res://scripts/tactical_defs.gd")
	if rules == null or defs == null or not rules.can_instantiate() or not defs.can_instantiate():
		expect(false, "tactical modules must compile before scenarios can run")
		finish()
		return
	check_catalog()
	check_patterns()
	check_counter_and_order()
	check_dodge_punish()
	check_defence_and_distance()
	check_armor_and_simultaneous()
	check_passives()
	check_cross_turn_and_errors()
	check_all_pairings()
	finish()

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures.append(label)

func finish() -> void:
	for failure in failures:
		print("FAIL: ", failure)
	print("TACTICAL RULES CHECK: %d/%d passed" % [checks - failures.size(), checks])
	quit(0 if failures.is_empty() else 1)

func context() -> Dictionary:
	return {"round_id": 1, "turn": 1, "action_count":3, "distance": 0,
		"player": {"hp":100,"rage":0.0,"jokers":[],"exposed":false,"focus":false,"dodge_charge":false,"tempo":0,"extra_draw":0,"previous_hit":false},
		"foe": {"hp":100,"rage":0.0,"jokers":[],"exposed":false,"focus":false,"dodge_charge":false,"tempo":0,"extra_draw":0,"previous_hit":false}}

func combat(p: Array, e: Array, ctx: Dictionary = {}) -> Dictionary:
	return rules.resolve_exchange(p, e, context() if ctx.is_empty() else ctx)

func hits(result: Dictionary, kind: String = "") -> Array:
	var out: Array = []
	for beat in result.get("events", []):
		for group in beat.get("groups", []):
			for hit in group.get("hits", []):
				if kind == "" or hit.kind == kind:
					out.append(hit)
	return out

func first_hit(result: Dictionary, kind: String) -> Dictionary:
	var found := hits(result, kind)
	return {} if found.is_empty() else found[0]

func check_catalog() -> void:
	expect(defs.card_ids().size() == 18, "18 usable action types")
	expect(defs.deck().size() == 36, "36 finite physical cards")
	expect(defs.joker_ids().size() == 8, "eight unique Joker definitions")
	var base = load("res://scripts/card_data.gd")
	for id in defs.card_ids():
		var card: Dictionary = defs.card(id)
		expect(int(card.rank) >= 1 and int(card.rank) <= 9, "rank valid: " + id)
		expect(not base.card(String(card.clip)).is_empty(), "existing visual clip: " + id)
		expect(defs.deck().count(id) == 2, "two physical copies: " + id)
	expect(base.CARDS.size() == 12, "original realtime catalog stays at twelve")

func check_patterns() -> void:
	var triple: Dictionary = defs.evaluate(["jab", "jab", "feint"],3)
	var sequence: Dictionary = defs.evaluate(["uppercut", "jab", "cross"],3)
	var pair: Dictionary = defs.evaluate(["sidestep", "cross", "focus"],3)
	var scatter: Dictionary = defs.evaluate(["jab", "guard", "backstep"],3)
	expect(triple.type == "triple" and triple.flat == 3 and is_equal_approx(triple.mult,1.25), "triple +3 x1.25")
	expect(sequence.type == "sequence" and sequence.flat == 2 and is_equal_approx(sequence.mult,1.15), "unordered straight +2 x1.15")
	expect(pair.type == "pair" and pair.flat == 1, "pair is useful +1")
	expect(scatter.type == "scatter" and scatter.flat == 0, "scatter no automatic winner")

func check_counter_and_order() -> void:
	var r := combat(["jab","focus","guard"],["uppercut","focus","guard"])
	expect(first_hit(r,"counter").get("damage",0) == 5, "jab catches uppercut startup for 4x1.25")
	expect(r.next_state.player.hp == 100 and r.next_state.foe.hp == 95, "counter interrupts only the current uppercut")
	expect(hits(r,"counter").size() == 1, "one true counter event")
	var swapped := combat(["focus","jab","guard"],["uppercut","jab","guard"])
	expect(swapped.next_state.player.hp < 100, "changing card order changes exchange result")
	var charge := combat(["jab","guard","backstep"],["focus","cross","guard"])
	expect(charge.next_state.player.hp == 99, "interrupted focus does not create a charge")

func check_dodge_punish() -> void:
	var r := combat(["sidestep","cross","focus"],["uppercut","jab","focus"])
	expect(hits(r,"dodged").size() == 1, "sidestep really dodges an attack")
	expect(first_hit(r,"punish").get("damage",0) == 10, "dodge into cross = 6+pair1+punish3")
	expect(r.next_state.player.hp == 100 and r.next_state.foe.hp == 90, "dodge-riposte defeats the incoming fast jab")
	expect(hits(r,"counter").is_empty(), "punish and counter are mutually exclusive")
	var no_attack := combat(["sidestep","cross","focus"],["guard","jab","focus"])
	expect(hits(no_attack,"dodged").is_empty() and hits(no_attack,"punish").filter(func(hit): return hit.source=="player").is_empty(), "empty dodge creates no reward for the defender")
	var feint := combat(["feint","cross","focus"],["guard","jab","focus"])
	expect(hits(feint,"punish").size() == 1, "feint baits guard into a real opening")

func check_defence_and_distance() -> void:
	var guard := combat(["guard","focus","backstep"],["jab","focus","guard"])
	expect(guard.next_state.player.hp == 99 and hits(guard,"blocked").size() == 1, "guard reduces damage 80% with minimum chip1")
	var close := context()
	close.distance = 0
	var throw_result := combat(["throw","focus","guard"],["guard","focus","backstep"], close)
	expect(throw_result.next_state.foe.hp == 92 and hits(throw_result,"blocked").is_empty(), "close throw bypasses guard")
	var parry := combat(["parry","cross","guard"],["uppercut","jab","guard"])
	expect(hits(parry,"parried").size() == 1 and hits(parry,"punish").size() == 1, "parry creates riposte")
	var delayed := combat(["sidestep","guard","focus"],["delayed_heavy","guard","focus"])
	expect(hits(delayed,"dodged").is_empty() and delayed.next_state.player.hp < 100, "delay catches sidestep")
	var delayed_parry := combat(["parry","guard","focus"],["delayed_heavy","guard","focus"])
	expect(hits(delayed_parry,"parried").is_empty() and delayed_parry.next_state.player.hp < 100, "delay catches parry")
	var breaker := combat(["guard","focus","backstep"],["guard_break","focus","guard"])
	expect(hits(breaker,"blocked").is_empty() and breaker.next_state.player.hp == 92, "guard break bypasses guard")
	var middle := context()
	middle.distance = 1
	var range_result := combat(["backstep","wave","focus"],["sweep","guard","focus"],middle)
	expect(range_result.next_state.distance == 2 and hits(range_result,"whiff").size() == 1, "backstep causes out-of-range whiff")
	expect(hits(range_result,"punish").size() == 1 and range_result.next_state.foe.hp < 100, "wave can punish from far")
	var far := context()
	far.distance = 2
	var throw_far := combat(["throw","focus","guard"],["guard","focus","backstep"],far)
	expect(throw_far.next_state.foe.hp == 100, "throw cannot magically reach far")

func check_armor_and_simultaneous() -> void:
	var armor := combat(["jab","focus","guard"],["armored_heavy","focus","guard"])
	expect(hits(armor,"counter").size() == 1 and armor.next_state.player.hp == 90 and armor.next_state.foe.hp == 95, "armor trades damage instead of cancelling")
	var close := context()
	close.distance = 0
	var throw_armor := combat(["throw","focus","guard"],["armored_heavy","focus","guard"],close)
	expect(throw_armor.next_state.player.hp == 100, "throw interrupts armor")
	var simultaneous := combat(["jab","focus","guard"],["jab","focus","guard"])
	expect(simultaneous.next_state.player.hp == 96 and simultaneous.next_state.foe.hp == 96, "same-speed attacks trade atomically")
	expect(hits(simultaneous,"counter").is_empty(), "same-speed trade is not a counter")
	var ko := context()
	ko.player.hp = 3
	ko.foe.hp = 3
	var double_ko := combat(["jab","wave","uppercut"],["jab","wave","uppercut"],ko)
	expect(double_ko.next_state.player.hp == 0 and double_ko.next_state.foe.hp == 0, "same contact allows double KO")
	expect(double_ko.events.size() == 1, "KO truncates remaining beats")

func check_passives() -> void:
	var a := context()
	a.player.jokers = ["shadow","opening","wind"]
	var b := context()
	b.player.jokers = ["opening","shadow","wind"]
	var ra := combat(["sidestep","jab","backstep"],["uppercut","cross","guard"],a)
	var rb := combat(["sidestep","jab","backstep"],["uppercut","cross","guard"],b)
	expect(first_hit(ra,"punish").get("damage",0) == 13, "add3 then x1.25 rounds to13")
	expect(first_hit(rb,"punish").get("damage",0) == 12, "x1.25 then add3 rounds to12")
	expect(ra.next_state.player.extra_draw == 1, "successful evade grants one next-turn draw")
	var multiple := combat(["sidestep","sidestep","parry"],["uppercut","uppercut","jab"],a)
	expect(multiple.next_state.player.extra_draw == 1, "wind Joker only triggers once per exchange")
	var missed := combat(["sidestep","guard","focus"],["guard","guard","focus"],a)
	expect(missed.next_state.player.extra_draw == 0, "no attack means no phantom draw trigger")
	var c := context()
	c.player.jokers = ["counter","pressure","breaker"]
	var rc := combat(["jab","cross","guard"],["uppercut","uppercut","guard"],c)
	expect(hits(rc,"counter").size()==1 and hits(rc,"punish").size()==1 and rc.events[1].actions.player.start==2, "pressure and a valid link turn the following attack into a timely punish")
	expect(first_hit(rc,"counter").get("damage",0) == 8, "counter Joker adds after counter multiplier")

func check_cross_turn_and_errors() -> void:
	var c := context()
	var before := c.duplicate(true)
	var r := combat(["guard","focus","sidestep"],["guard","focus","uppercut"],c)
	expect(r.next_state.foe.exposed, "third-beat evade leaves next-turn opening")
	expect(c == before, "pure resolver never mutates its caller context")
	var next: Dictionary = r.next_state.duplicate(true)
	next.turn = 2
	var riposte := combat(["cross","focus","guard"],["jab","focus","guard"],next)
	expect(not hits(riposte,"punish").is_empty(), "opening survives across the turn boundary")
	var recovery := combat(["cross","guard","focus"],["recover","guard","focus"],next)
	expect(recovery.events[0].actions.foe.wait==8 and not hits(recovery,"punish").is_empty(), "recover removes only four frames of a long opening")
	var invalid := combat(["jab","bad","guard"],["jab","focus","guard"])
	expect(invalid.has("error") and invalid.events.is_empty(), "unknown card rejected without partial resolution")
	var short := combat(["jab"],["jab","focus","guard"])
	expect(short.has("error"), "incomplete plan rejected")

func check_all_pairings() -> void:
	for distance in range(3):
		for p in defs.card_ids():
			for e in defs.card_ids():
				var ctx := context()
				ctx.action_count = 5
				ctx.distance = distance
				var r := combat([p,"focus","guard","focus","guard"],[e,"focus","guard","focus","guard"],ctx)
				var reverse := combat([e,"focus","guard","focus","guard"],[p,"focus","guard","focus","guard"],ctx)
				expect(r.events.size() <= 5 and r.next_state.player.hp >= 0 and r.next_state.foe.hp >= 0, "bounded five-beat paired resolution: %s/%s/%d" % [p,e,distance])
				expect(r.next_state.player.hp == reverse.next_state.foe.hp and r.next_state.foe.hp == reverse.next_state.player.hp, "side-neutral resolution: %s/%s/%d" % [p,e,distance])
