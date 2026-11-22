extends RefCounted
## Only the AI's own hand and a public combat snapshot enter these functions.
const Defs = preload("res://scripts/tactical_defs.gd")
const Rules = preload("res://scripts/tactical_rules.gd")
const BEAM_PER_STYLE := 8
const CANDIDATES_PER_STYLE := 3
const SAMPLES := [
	["rush","jab","cross","uppercut","guard"], ["sidestep","cross","pursuit","guard","recover"],
	["guard","jab","cross","guard_break","recover"], ["rush","throw","sidestep","jab","recover"],
	["backstep","wave","guard","wave","recover"], ["feint","cross","pursuit","guard","jab"],
	["parry","cross","pursuit","uppercut","guard"], ["armored_heavy","guard","delayed_heavy","sweep","recover"],
]
const LOADOUTS := [["shadow","opening","wind"],["counter","pressure","sequence"],["triple","sequence","breaker"]]

static func choose_loadout(offers: Array, seed_value: int = 1) -> Array:
	var best: Array = []
	for offset in range(LOADOUTS.size()):
		var group: Array = LOADOUTS[(absi(seed_value)+offset)%LOADOUTS.size()]
		var available: Array = []
		for id in group:
			if offers.has(id):
				available.append(id)
		if available.size() > best.size():
			best = available
	for id in offers:
		if best.size() >= Defs.JOKER_SLOTS:
			break
		if not best.has(id):
			best.append(id)
	return best

static func choose_plan(hand: Array, public_context: Dictionary, role: String) -> Array:
	var candidates: Array = _candidates(hand,public_context,role)
	if candidates.is_empty():
		return []
	var action_count := int(public_context.get("action_count",Defs.PLAY))
	var samples: Array = []
	for template in SAMPLES:
		var sample: Array = []
		for index in range(action_count):
			sample.append(template[index%template.size()])
		samples.append(sample)
	var history: Array = public_context.get("history",[])
	for entry in history.slice(maxi(0,history.size()-3)):
		var revealed: Array = entry.get(Rules.opponent(role),[])
		if revealed.size() == action_count and not samples.has(revealed):
			samples.append(revealed.duplicate())
	# Only publicly visible cards constrain the player's simulation samples.
	# The enemy never receives the player's pending hand or action order.
	var preview: Array = public_context.get("opponent_preview",[])
	for sample in samples:
		for index in range(mini(preview.size(),sample.size())):
			if preview[index] != null:
				sample[index] = preview[index]
	var best_score := -INF
	var best: Array = []
	var tied := 0
	var random := RandomNumberGenerator.new()
	random.seed = int(public_context.get("decision_seed",1))
	for candidate in candidates:
		var score := 0.0
		for sample in samples:
			var result: Dictionary = Rules.resolve_exchange(candidate.ids,sample,public_context) if role == "player" else Rules.resolve_exchange(sample,candidate.ids,public_context)
			if result.has("error"):
				continue
			score += _score_state(public_context,result.next_state,role)
		if score > best_score+0.00001:
			best_score = score
			best = candidate.indices.duplicate()
			tied = 1
		elif absf(score-best_score) <= 0.00001:
			tied += 1
			if random.randi_range(1,tied) == 1:
				best = candidate.indices.duplicate()
	return best

static func _score_state(before: Dictionary,after: Dictionary,role: String) -> float:
	var target: String = Rules.opponent(role)
	var score := float(int(before[target].hp)-int(after[target].hp)-int(before[role].hp)+int(after[role].hp))
	if int(after.player.hp)>0 and int(after.foe.hp)>0 and int(before.get("turn",1))<Defs.TURNS:
		var capacity := Defs.HAND_MAX-Defs.HAND
		score += float(clampi(int(after[role].extra_draw),0,capacity)-clampi(int(after[target].extra_draw),0,capacity))
		score += 0.25*float(int(after[target].ready_delay)-int(after[role].ready_delay))
	return score

static func _gear_effects(gear: Array) -> Array:
	var out: Array = []
	for id in gear:
		out.append_array(Defs.joker(String(id)).effects)
	return out

static func choose_discards(hand: Array, public_context: Dictionary, role: String) -> Array:
	var candidates: Array = _candidates(hand,public_context,role)
	if candidates.is_empty():
		return []
	candidates.sort_custom(_quality_sort)
	var keep: Array = candidates[0].indices
	var ranks: Array = Defs.evaluate(candidates[0].ids,candidates[0].ids.size()).ranks
	var options: Array = []
	var gear: Array = _gear_effects(public_context[role].jokers)
	for index in range(hand.size()):
		if keep.has(index) or hand[index] == null:
			continue
		var card: Dictionary = Defs.card(String(hand[index]))
		var value := float(card.damage)*0.3+(2.0 if card.kind == "guard" else 0.0)
		if ranks.has(int(card.rank)):
			value += 2.0
		if int(public_context.distance) == 2 and card.range == "projectile":
			value += 3.0
		value += _gear_affinity(card,{},gear)
		options.append({"index":index,"value":value})
	options.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
		return a.index < b.index if is_equal_approx(float(a.value),float(b.value)) else float(a.value)<float(b.value))
	var out: Array = []
	for item in options.slice(0,Defs.DISCARD_MAX):
		out.append(item.index)
	return out

static func _quality_sort(a: Dictionary,b: Dictionary) -> bool:
	return String(a.key)<String(b.key) if is_equal_approx(float(a.quality),float(b.quality)) else float(a.quality)>float(b.quality)

static func _candidates(hand: Array, context: Dictionary, role: String) -> Array:
	# Expand a small beam per opening style instead of enumerating 10P5 plans.
	# At most 24 complete plans enter expensive full-combat simulation.
	var action_count := int(context.get("action_count",Defs.PLAY))
	var catalog := {}
	var valid := 0
	for id in hand:
		if id==null:
			continue
		if not catalog.has(String(id)):
			catalog[String(id)] = Defs.card(String(id))
		valid += 1 if not catalog[String(id)].is_empty() else 0
	if action_count<1 or valid<action_count:
		return []
	var gear: Array = _gear_effects(context[role].jokers)
	var beam: Array = [{"indices":[],"ids":[],"key":"","quality":0.0}]
	for depth in range(action_count):
		var expanded: Array = []
		var seen := {}
		for candidate in beam:
			for index in range(hand.size()):
				if hand[index] == null or candidate.indices.has(index) or catalog[String(hand[index])].is_empty():
					continue
				var indices: Array = candidate.indices.duplicate()
				var ids: Array = candidate.ids.duplicate()
				indices.append(index)
				ids.append(String(hand[index]))
				var key := "/".join(PackedStringArray(ids))
				if seen.has(key):
					continue
				seen[key] = true
				expanded.append({"indices":indices,"ids":ids,"key":key,"quality":_quality(ids,context,catalog,gear)})
		beam = _prune(expanded,CANDIDATES_PER_STYLE if depth == action_count-1 else BEAM_PER_STYLE)
	return beam

static func _prune(candidates: Array,limit: int) -> Array:
	var buckets := {}
	for candidate in candidates:
		var category := String(Defs.TIMING[candidate.ids[0]].ai_style)
		if not buckets.has(category):
			buckets[category] = []
		buckets[category].append(candidate)
	var out: Array = []
	var categories: Array = buckets.keys()
	categories.sort()
	for category in categories:
		buckets[category].sort_custom(_quality_sort)
		out.append_array(buckets[category].slice(0,limit))
	return out

static func _quality(ids: Array, context: Dictionary, catalog: Dictionary, gear: Array) -> float:
	var pattern: Dictionary = Defs.evaluate(ids,ids.size())
	var score := float(pattern.flat)*3.0+(float(pattern.mult)-1.0)*20.0
	var attacks := 0
	var distance := int(context.distance)
	var chain := false
	var points := 0
	for index in range(ids.size()):
		var card: Dictionary = catalog[ids[index]]
		var projected := maxi(0,distance-1) if card.follow and chain else distance
		if card.attack:
			attacks += 1
			score += float(card.damage)*0.45
			score -= float(card.whiff_recover)*0.08
			if projected<int(card.range_min) or projected>int(card.range_max):
				score -= 8.0
			elif distance==2 and card.range=="projectile":
				score += 3.0
			if chain and card.combo_role in ["linker","starter_linker","ender"] and points+int(card.combo_cost)<=Defs.COMBO_BUDGET:
				points += int(card.combo_cost)
				score += 2.0
				chain = card.combo_role!="ender"
			elif card.combo_role in ["starter","starter_linker"] and points<Defs.COMBO_BUDGET:
				chain = true
				points += 1
			else:
				chain = false
		else:
			chain = false
		for effect in card.get("on_ready",[]):
			if effect.op=="distance" and (effect.get("when","")!="follow" or projected!=distance):
				distance = clampi(distance+int(effect.value),0,2)
		score += _gear_affinity(card,pattern,gear)
		if index+1 < ids.size():
			var next: Dictionary = catalog[ids[index+1]]
			if (card.defense != "" or card.tags.has("feint")) and next.attack:
				score += 3.0
			if card.tags.has("advance") and next.range == "throw":
				score += 4.0
			if card.tags.has("retreat") and next.range == "projectile":
				score += 4.0
			if card.tags.has("focus") and next.attack:
				score += 2.0
	if attacks == 0:
		score -= 5.0
	return score

static func _gear_affinity(card: Dictionary,pattern: Dictionary,gear: Array) -> float:
	var score := 0.0
	for effect in gear:
		if effect.get("when","") == "shadow_ready" and card.defense == "dodge":
			score += 3.0
		elif effect.get("when","") == "counter" and card.attack and int(card.windup)<=6:
			score += 1.0
		elif effect.get("when","") == "pattern_tag" and pattern.get("tags",[]).has(effect.tag):
			score += 1.0
		elif effect.event == "defend" and card.defense in ["dodge","parry"]:
			score += 2.0
		elif effect.has("requires_tag") and card.tags.has(effect.requires_tag):
			score += 2.0
	return score
