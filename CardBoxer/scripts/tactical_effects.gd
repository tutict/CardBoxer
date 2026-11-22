extends RefCounted
## Small, data-driven hooks shared by every action and Joker definition.
const Defs = preload("res://scripts/tactical_defs.gd")

static func _target(role: String,effect: Dictionary) -> String:
	return ("foe" if role == "player" else "player") if effect.get("target","self") == "opponent" else role

static func _state_effect(effect: Dictionary,role: String,ctx: Dictionary) -> int:
	if effect.op == "distance":
		return int(effect.value)
	var owner: String = _target(role,effect)
	var stat := String(effect.stat)
	if effect.op == "set":
		ctx[owner][stat] = effect.value
	elif effect.op == "add":
		ctx[owner][stat] = int(ctx[owner].get(stat,0))+int(effect.value)
	elif effect.op == "reduce":
		ctx[owner][stat] = maxi(0,int(ctx[owner].get(stat,0))-int(effect.value))
	return 0

static func apply_start(card: Dictionary,role: String,ctx: Dictionary) -> void:
	for effect in card.get("on_start",[]):
		_state_effect(effect,role,ctx)

static func apply_ready(card: Dictionary,role: String,victim: Dictionary,ctx: Dictionary,follow: bool) -> int:
	var distance := 0
	for effect in card.get("on_ready",[]):
		if effect.get("when","") == "follow" and not follow:
			continue
		if effect.has("if_defenses") and not effect.if_defenses.has(victim.get("defense","")):
			continue
		distance += _state_effect(effect,role,ctx)
	return distance

static func _matches(effect: Dictionary,action: Dictionary,pattern: Dictionary,kind: String) -> bool:
	match String(effect.get("when","")):
		"": return true
		"follow": return bool(action.get("pursuit",false))
		"shadow_ready": return bool(action.get("shadow_ready",false))
		"pattern_tag": return pattern.get("tags",[]).has(effect.tag)
		_: return effect.when == kind

static func card_modifiers(action: Dictionary,kind: String) -> Array:
	var out: Array = []
	for effect in action.card.get("damage_effects",[]):
		if _matches(effect,action,{},kind):
			out.append({"name":effect.name,"op":effect.op,"value":effect.value})
	return out

static func joker_modifiers(action: Dictionary,state: Dictionary,pattern: Dictionary,kind: String) -> Array:
	var out: Array = []
	for id in state.jokers:
		var joker: Dictionary = Defs.joker(id)
		for effect in joker.effects:
			if effect.event == "damage" and _matches(effect,action,pattern,kind):
				out.append({"name":joker.name,"op":effect.op,"value":effect.value})
	return out

static func contact(hit: Dictionary,actions: Dictionary,ctx: Dictionary,used: Dictionary) -> Array:
	var out: Array = []
	var defender: String = hit.target
	var draw := int(actions[defender].card.get("block_draw",0))
	if hit.kind == "blocked" and draw>0 and not used[defender].has("guard_draw"):
		used[defender]["guard_draw"] = true
		ctx[defender].extra_draw += draw
		out.append({"role":defender,"id":"guard_draw","name":"格挡","value":draw})
	for role in [String(hit.source),String(hit.target)]:
		var event := "attack" if role == hit.source else "defend"
		for id in ctx[role].jokers:
			var joker: Dictionary = Defs.joker(id)
			for effect in joker.effects:
				if effect.event != event or not effect.kinds.has(hit.kind):
					continue
				if effect.has("requires_tag") and not actions[hit.source].card.get("tags",[]).has(effect.requires_tag):
					continue
				if effect.get("once",false) and used[role].has(id):
					continue
				if effect.get("once",false):
					used[role][id] = true
				var amount := 0
				for state_effect in effect.state_effects:
					_state_effect(state_effect,role,ctx)
					amount += int(state_effect.value)
				out.append({"role":role,"id":id,"name":joker.name,"value":amount})
	return out
