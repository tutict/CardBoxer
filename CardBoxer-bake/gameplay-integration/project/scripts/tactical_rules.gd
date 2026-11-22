extends RefCounted
## Pure ordered combat. All time is integer action order, never render delta.
const Defs = preload("res://scripts/tactical_defs.gd")
const Effects = preload("res://scripts/tactical_effects.gd")
const ROLES := ["player","foe"]

static func default_state() -> Dictionary:
	return {"hp":Defs.HP,"rage":0.0,"jokers":[],"exposed":false,"focus":false,"dodge_charge":false,"tempo":0,"extra_draw":0,"previous_hit":false,"ex_active":false}

static func default_context() -> Dictionary:
	return {"round_id":1,"turn":1,"action_count":Defs.PLAY,"distance":1,"player":default_state(),"foe":default_state()}

static func opponent(role: String) -> String:
	return "foe" if role == "player" else "player"

static func resolve_exchange(player_plan: Array, enemy_plan: Array, context: Dictionary) -> Dictionary:
	var plans := {"player":player_plan,"foe":enemy_plan}
	var action_count := int(context.get("action_count",Defs.PLAY))
	if action_count < 1 or action_count > Defs.HAND_MAX:
		return _error("Invalid action count",context)
	for role in ROLES:
		if plans[role].size() != action_count:
			return _error("Each plan must contain %d actions" % action_count,context)
		for id in plans[role]:
			if Defs.card(String(id)).is_empty():
				return _error("Unknown tactical card: " + String(id),context)
	var ctx: Dictionary = default_context()
	for key in context:
		ctx[key] = context[key].duplicate(true) if context[key] is Dictionary or context[key] is Array else context[key]
	ctx.distance = clampi(int(ctx.distance),0,2)
	var patterns: Dictionary = {}
	var used := {"player":{},"foe":{}}
	for role in ROLES:
		if not ctx[role] is Dictionary:
			return _error("Invalid fighter state",context)
		var defaults: Dictionary = default_state()
		for key in defaults:
			if not ctx[role].has(key):
				ctx[role][key] = defaults[key]
		var seen: Array = []
		for joker_id in ctx[role].jokers:
			if not Defs.JOKER_IDS.has(joker_id) or seen.has(joker_id):
				return _error("Invalid or duplicate Joker",context)
			seen.append(joker_id)
		if seen.size() > Defs.JOKER_SLOTS:
			return _error("At most three Jokers",context)
		ctx[role].hp = clampi(int(ctx[role].hp),0,Defs.HP)
		ctx[role].extra_draw = 0
		patterns[role] = Defs.evaluate(plans[role],action_count)
		ctx[role].ex_active = float(ctx[role].rage) >= 100.0
		if ctx[role].ex_active:
			ctx[role].rage = 0.0
			patterns[role].flat += 1
			patterns[role].mult += 0.1
			patterns[role].ex = true
	var beats: Array = []
	for index in range(action_count):
		if int(ctx.player.hp) <= 0 or int(ctx.foe.hp) <= 0:
			break
		var ids := {"player":String(player_plan[index]),"foe":String(enemy_plan[index])}
		var beat: Dictionary = _resolve_beat(ids,ctx,patterns,used,index)
		beats.append(beat)
	return {"events":beats,"next_state":ctx,"patterns":patterns}

static func _error(message: String, context: Dictionary) -> Dictionary:
	return {"error":message,"events":[],"next_state":context.duplicate(true),"patterns":{}}

static func _reachable(card: Dictionary, distance: int) -> bool:
	if String(card.range) == "projectile":
		return true
	return distance == 0 if String(card.range) == "throw" else distance <= 1

static func _resolve_beat(ids: Dictionary, ctx: Dictionary, patterns: Dictionary, used: Dictionary, index: int) -> Dictionary:
	var before: Dictionary = ctx.duplicate(true)
	for role in ROLES:
		Effects.apply_start(Defs.card(ids[role]),role,ctx)
	var prior := {"player":bool(ctx.player.exposed),"foe":bool(ctx.foe.exposed)}
	for role in ROLES:
		ctx[role].exposed = false
	var actions: Dictionary = {}
	var frames: Array[int] = []
	for role in ROLES:
		var card: Dictionary = Defs.card(ids[role])
		var tempo := int(ctx[role].tempo) if bool(card.attack) else 0
		var start := maxi(1,int(card.windup)-tempo)
		var pursuit: bool = bool(card.follow) and (bool(before[role].previous_hit) or bool(prior[opponent(role)]))
		var reach_distance := maxi(0,int(ctx.distance)-1) if pursuit else int(ctx.distance)
		var punish: bool = bool(card.attack) and bool(prior[opponent(role)]) and _reachable(card,reach_distance)
		if punish:
			start = 0
		actions[role] = {"id":ids[role],"clip":card.clip,"card":card,"start":start,"ready":false,"cancelled":false,"cancel_frame":-1,"punish":punish,"pursuit":pursuit,"charged":bool(ctx[role].focus) if card.attack else false,"shadow_ready":bool(ctx[role].dodge_charge) if card.attack else false}
		ctx[role].tempo = 0
		if bool(card.attack):
			# A committed attack spends its charge even if it is interrupted or misses.
			ctx[role].focus = false
			ctx[role].dodge_charge = false
		if not frames.has(start):
			frames.append(start)
	frames.sort()
	var groups: Array = []
	var landed := {"player":false,"foe":false}
	for frame in frames:
		var changes: Array = []
		var attack_roles: Array = []
		var distance_change := 0
		# Actions completing at the same moment are established together.
		for role in ROLES:
			var action: Dictionary = actions[role]
			if action.cancelled or int(action.start) != frame or int(ctx[role].hp) <= 0:
				continue
			action.ready = true
			distance_change += Effects.apply_ready(action.card,role,actions[opponent(role)].card,ctx,bool(action.pursuit))
			if bool(action.card.attack):
				attack_roles.append(role)
				continue
			changes.append({"role":role,"kind":action.id})
		ctx.distance = clampi(int(ctx.distance)+distance_change,0,2)
		var hit_list: Array = []
		for role in attack_roles:
			var hit: Dictionary = _contact(role,actions,ctx,patterns)
			hit_list.append(hit)
		# Calculate every simultaneous contact before mutating either HP value.
		for hit in hit_list:
			var source: String = hit.source
			var target: String = hit.target
			if int(hit.damage) > 0:
				ctx[target].hp = maxi(0,int(ctx[target].hp)-int(hit.damage))
				ctx[target].rage = clampf(float(ctx[target].rage)+float(hit.damage)*5.0,0.0,100.0)
				if bool(hit.interrupt):
					actions[target].cancelled = true
					actions[target].cancel_frame = frame
			if hit.kind in ["dodged","parried","whiff"]:
				ctx[source].exposed = true
			if hit.kind == "dodged":
				ctx[target].dodge_charge = true
			if hit.kind in ["hit","counter","punish"] and String(actions[source].card.range) != "projectile":
				landed[source] = true
			hit["triggers"] = Effects.contact(hit,actions,ctx,used)
			hit["after_hp"] = int(ctx[target].hp)
			hit["event_id"] = "%d:%d:%d:%d:%s" % [int(ctx.round_id),int(ctx.turn),index,frame,source]
		var terminal: bool = int(ctx.player.hp) <= 0 or int(ctx.foe.hp) <= 0
		if not changes.is_empty() or not hit_list.is_empty():
			groups.append({"frame":frame,"hits":hit_list,"changes":changes,"state":ctx.duplicate(true),"terminal":terminal})
		if terminal:
			break
	for role in ROLES:
		ctx[role].previous_hit = bool(landed[role])
	var terminal: bool = int(ctx.player.hp) <= 0 or int(ctx.foe.hp) <= 0
	return {"event_id":"%d:%d:%d" % [int(ctx.round_id),int(ctx.turn),index],"beat":index+1,"actions":actions,"before":before,"after":ctx.duplicate(true),"groups":groups,"terminal":terminal}

static func _contact(role: String, actions: Dictionary, ctx: Dictionary, patterns: Dictionary) -> Dictionary:
	var target: String = opponent(role)
	var action: Dictionary = actions[role]
	var victim: Dictionary = actions[target]
	var card: Dictionary = action.card
	var kind := "hit"
	var ready: bool = bool(victim.ready) and not bool(victim.cancelled)
	if not _reachable(card,int(ctx.distance)):
		kind = "whiff"
	elif ready and victim.card.defense == "dodge" and not card.ignore_defenses.has("dodge"):
		kind = "dodged"
	elif ready and victim.card.defense == "parry" and card.range == "melee" and not card.ignore_defenses.has("parry"):
		kind = "parried"
	elif ready and victim.card.defense == "block" and not card.ignore_defenses.has("block"):
		kind = "blocked"
	elif bool(action.punish):
		kind = "punish"
	elif bool(victim.card.attack) and not victim.ready:
		kind = "counter"
	var parts: Array = []
	var raw := 0.0
	if kind not in ["whiff","dodged","parried"]:
		raw = _damage(action,ctx[role],patterns[role],kind,parts)
	var rolled := maxi(1,int(round(raw))) if raw > 0.0 else 0
	var damage := mini(rolled,int(ctx[target].hp))
	var armor: bool = bool(victim.card.armor) and not bool(card.breaks_armor)
	var interrupt: bool = damage > 0 and not victim.ready and not armor
	return {"source":role,"target":target,"card_id":action.id,"clip":action.clip,"kind":kind,"damage":damage,"rolled_damage":rolled,"raw_damage":raw,"parts":parts,"interrupt":interrupt,"before_hp":int(ctx[target].hp)}

static func _part(parts: Array, name: String, op: String, amount: float, before: float) -> float:
	var after := before+amount if op == "+" else (before*amount if op == "×" else amount)
	parts.append({"name":name,"op":op,"value":amount,"before":before,"after":after})
	return after

static func _damage(action: Dictionary, state: Dictionary, pattern: Dictionary, kind: String, parts: Array) -> float:
	var value := _part(parts,"招式","base",float(action.card.damage),0.0)
	if int(pattern.flat) != 0:
		value = _part(parts,String(pattern.name),"+",float(pattern.flat),value)
	if action.charged:
		value = _part(parts,"蓄势","+",3.0,value)
	for modifier in Effects.card_modifiers(action,kind):
		value = _part(parts,String(modifier.name),String(modifier.op),float(modifier.value),value)
	if kind == "punish":
		value = _part(parts,"确反","+",3.0,value)
	if not is_equal_approx(float(pattern.mult),1.0):
		value = _part(parts,"EX牌型" if pattern.ex else "牌型","×",float(pattern.mult),value)
	if kind == "counter":
		value = _part(parts,"打康","×",1.25,value)
	for modifier in Effects.joker_modifiers(action,state,pattern,kind):
		value = _part(parts,String(modifier.name),String(modifier.op),float(modifier.value),value)
	if kind == "blocked":
		value = _part(parts,"格挡","×",0.2,value)
	return value
