extends RefCounted
## Pure ordered combat. All time is integer action order, never render delta.
const Defs = preload("res://scripts/tactical_defs.gd")
const Effects = preload("res://scripts/tactical_effects.gd")
const ROLES := ["player","foe"]

static func default_state() -> Dictionary:
	return {"hp":Defs.HP,"rage":0.0,"jokers":[],"exposed":false,"ready_delay":0,"recovery":{},"combo":{"open":false,"used":0},"focus":false,"dodge_charge":false,"tempo":0,"extra_draw":0,"previous_hit":false,"ex_active":false}

static func default_context() -> Dictionary:
	return {"round_id":1,"turn":1,"action_count":Defs.PLAY,"distance":1,"player":default_state(),"foe":default_state()}

static func opponent(role: String) -> String:
	return "foe" if role == "player" else "player"

static func resolve_exchange(player_plan: Array, enemy_plan: Array, context: Dictionary) -> Dictionary:
	var plans := {"player":player_plan,"foe":enemy_plan}
	var action_count := int(context.get("action_count",Defs.PLAY))
	if action_count < 1 or action_count > Defs.HAND_MAX:
		return _error("Invalid action count",context)
	var catalog := {}
	for role in ROLES:
		if plans[role].size() != action_count:
			return _error("Each plan must contain %d actions" % action_count,context)
		for id in plans[role]:
			if not catalog.has(String(id)):
				catalog[String(id)] = Defs.card(String(id))
			if catalog[String(id)].is_empty():
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
				var value = defaults[key]
				ctx[role][key] = value.duplicate(true) if value is Dictionary or value is Array else value
		ctx[role].ready_delay = clampi(int(ctx[role].ready_delay),0,Defs.MAX_READY_DELAY)
		ctx[role].combo = {"open":false,"used":0}
		ctx[role].exposed = int(ctx[role].ready_delay)>0
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
		var beat: Dictionary = _resolve_beat(ids,ctx,patterns,used,index,catalog)
		beats.append(beat)
	# The last beat keeps its historical chain metadata; planning the next
	# exchange receives a fresh budget, not a phantom continuation opportunity.
	for role in ROLES:
		ctx[role].combo = {"open":false,"used":0}
	return {"events":beats,"next_state":ctx,"patterns":patterns}

static func _error(message: String, context: Dictionary) -> Dictionary:
	return {"error":message,"events":[],"next_state":context.duplicate(true),"patterns":{}}

static func _reachable(card: Dictionary, distance: int) -> bool:
	return distance>=int(card.range_min) and distance<=int(card.range_max)

static func _defense_active(action: Dictionary, frame: int) -> bool:
	if not action.ready or action.cancelled or action.card.defense == "":
		return false
	var window := int(action.card.get("defense_window",0))
	return window==0 or frame<int(action.start)+window

static func _prepare_action(role: String, card: Dictionary, ctx: Dictionary) -> Dictionary:
	var wait := int(ctx[role].ready_delay)
	var chain: Dictionary = ctx[role].combo
	var link_role: bool = card.combo_role in ["starter_linker","linker","ender"]
	var reach_distance := maxi(0,int(ctx.distance)-1) if card.follow else int(ctx.distance)
	var link: bool = card.attack and link_role and bool(chain.open) and int(chain.used)+int(card.combo_cost)<=Defs.COMBO_BUDGET and _reachable(card,reach_distance)
	var tempo := int(ctx[role].tempo) if card.attack else 0
	var start := wait+maxi(1,int(card.windup)-tempo-(Defs.COMBO_SPEED if link else 0))
	var pursuit: bool = card.follow and (link or (start<=int(ctx[opponent(role)].ready_delay) and _reachable(card,reach_distance)))
	var spent := int(chain.used)+int(card.combo_cost) if link else int(chain.used)
	var action := {"id":String(card.id),"clip":String(card.clip),"card":card,"wait":wait,"start":start,"ready_at":start+int(card.recover),"ready":false,"cancelled":false,"cancel_frame":-1,"punish":false,"pursuit":pursuit,"combo_applied":link,"combo_cost":int(card.combo_cost) if link else 0,"combo_used":spent,"charged":bool(ctx[role].focus) if card.attack else false,"shadow_ready":bool(ctx[role].dodge_charge) if card.attack else false,"recovery_start":start,"recovery_kind":"action","recovery_clip":String(card.clip),"carry":ctx[role].recovery.duplicate(true)}
	ctx[role].tempo = 0
	ctx[role].combo = {"open":link,"used":spent}
	if card.attack:
		# Charges are spent by the committed attempt, even when it misses/cancels.
		ctx[role].focus = false
		ctx[role].dodge_charge = false
	return action

static func _stun(action: Dictionary, hit: Dictionary, frame: int, duration: int, replace: bool, kind: String) -> void:
	var ready_at := frame+duration
	if replace or ready_at>=int(action.ready_at):
		action.ready_at = ready_at
		action.recovery_start = frame
		action.recovery_kind = kind
		action.recovery_clip = "block" if kind=="block" else ("hit_heavy" if hit.kind in ["counter","punish"] or int(hit.rolled_damage)>=8 else "hit_light")

static func _finish_timing(actions: Dictionary, ctx: Dictionary, handoff: int) -> int:
	var remaining := {}
	for role in ROLES:
		remaining[role] = maxi(0,int(actions[role].ready_at)-handoff)
	var common := mini(int(remaining.player),int(remaining.foe))
	for role in ROLES:
		var action: Dictionary = actions[role]
		var delay := mini(Defs.MAX_READY_DELAY,int(remaining[role])-common)
		ctx[role].ready_delay = delay
		ctx[role].exposed = delay>0
		action["next_delay"] = delay
		if delay==0:
			ctx[role].recovery = {}
		else:
			var elapsed := maxi(0,handoff+common-int(action.recovery_start))
			ctx[role].recovery = {"kind":String(action.recovery_kind),"clip":String(action.recovery_clip),"card_id":String(action.id),"elapsed":elapsed,"duration":elapsed+delay,"remaining":delay}
	return common

static func _resolve_beat(ids: Dictionary, ctx: Dictionary, patterns: Dictionary, used: Dictionary, index: int, catalog: Dictionary) -> Dictionary:
	var before: Dictionary = ctx.duplicate(true)
	for role in ROLES:
		Effects.apply_start(catalog[ids[role]],role,ctx)
	var actions: Dictionary = {}
	var frames: Array[int] = []
	for role in ROLES:
		var card: Dictionary = catalog[ids[role]]
		actions[role] = _prepare_action(role,card,ctx)
		if not frames.has(int(actions[role].start)):
			frames.append(int(actions[role].start))
	frames.sort()
	var groups: Array = []
	var landed := {"player":false,"foe":false}
	var incoming := {"player":false,"foe":false}
	for frame in frames:
		var changes: Array = []
		var attack_roles: Array = []
		var ready_roles: Array = []
		var distance_change := 0
		# Establish every simultaneous defense before evaluating any ready effects.
		for role in ROLES:
			var action: Dictionary = actions[role]
			if action.cancelled or int(action.start) != frame or int(ctx[role].hp) <= 0:
				continue
			action.ready = true
			ready_roles.append(role)
		for role in ready_roles:
			var action: Dictionary = actions[role]
			distance_change += Effects.apply_ready(action.card,role,actions[opponent(role)].card,ctx,bool(action.pursuit))
			if bool(action.card.attack):
				attack_roles.append(role)
				continue
			changes.append({"role":role,"kind":action.id})
		ctx.distance = clampi(int(ctx.distance)+distance_change,0,2)
		for role in ready_roles:
			var action: Dictionary = actions[role]
			var victim: Dictionary = actions[opponent(role)]
			var bait := int(action.card.get("bait_frames",0))
			if bait>0 and _reachable(action.card,int(ctx.distance)) and _defense_active(victim,frame):
				victim.ready_at = maxi(int(victim.ready_at),int(action.ready_at)+bait)
				victim.recovery_kind = "bait"
		var hit_list: Array = []
		for role in attack_roles:
			var hit: Dictionary = _contact(role,actions,ctx,patterns)
			hit_list.append(hit)
		# Calculate every simultaneous contact before mutating either HP value.
		var hit_distance := 0
		for hit in hit_list:
			var source: String = hit.source
			var target: String = hit.target
			var attacker: Dictionary = actions[source]
			var victim: Dictionary = actions[target]
			if int(hit.damage) > 0:
				ctx[target].hp = maxi(0,int(ctx[target].hp)-int(hit.damage))
				ctx[target].rage = clampf(float(ctx[target].rage)+float(hit.damage)*5.0,0.0,100.0)
				if bool(hit.interrupt):
					victim.cancelled = true
					victim.cancel_frame = frame
					_stun(victim,hit,frame,int(attacker.card.hitstun),true,"hit")
				elif hit.kind == "blocked":
					_stun(victim,hit,frame,int(attacker.card.blockstun),false,"block")
				elif not hit.armor:
					_stun(victim,hit,frame,int(attacker.card.hitstun),false,"hit")
			if hit.kind in ["dodged","parried","whiff"]:
				attacker.ready_at = frame+int(attacker.card.whiff_recover)
				attacker.recovery_start = frame
				attacker.recovery_kind = "whiff"
				if hit.kind == "parried":
					attacker.ready_at += int(victim.card.get("parry_penalty",0))
					victim.ready_at = int(victim.start)+int(victim.card.get("parry_recover",victim.card.recover))
			if hit.kind == "dodged":
				ctx[target].dodge_charge = true
			if hit.kind in ["hit","counter","punish"]:
				landed[source] = true
				incoming[target] = true
				hit_distance += int(attacker.card.get("hit_distance",0))
			hit["triggers"] = Effects.contact(hit,actions,ctx,used)
			hit["after_hp"] = int(ctx[target].hp)
			hit["event_id"] = "%d:%d:%d:%d:%s" % [int(ctx.round_id),int(ctx.turn),index,frame,source]
		ctx.distance = clampi(int(ctx.distance)+hit_distance,0,2)
		var terminal: bool = int(ctx.player.hp) <= 0 or int(ctx.foe.hp) <= 0
		if not changes.is_empty() or not hit_list.is_empty():
			groups.append({"frame":frame,"hits":hit_list,"changes":changes,"state":ctx.duplicate(true),"terminal":terminal})
		if terminal:
			break
	for role in ROLES:
		var action: Dictionary = actions[role]
		var can_continue: bool = bool(landed[role]) and not bool(incoming[role])
		ctx[role].previous_hit = can_continue
		var combo := {"open":false,"used":int(action.combo_used)}
		if can_continue:
			if action.combo_applied:
				combo.open = action.card.combo_role!="ender"
			elif action.card.combo_role in ["starter","starter_linker"] and int(action.combo_used)<Defs.COMBO_BUDGET:
				combo = {"open":true,"used":int(action.combo_used)+1}
				action.combo_cost = 1
				action.combo_used = int(combo.used)
		ctx[role].combo = combo
	var handoff := int(groups.back().frame) if not groups.is_empty() else 0
	var common := _finish_timing(actions,ctx,handoff)
	var terminal: bool = int(ctx.player.hp) <= 0 or int(ctx.foe.hp) <= 0
	return {"event_id":"%d:%d:%d" % [int(ctx.round_id),int(ctx.turn),index],"beat":index+1,"actions":actions,"before":before,"after":ctx.duplicate(true),"groups":groups,"handoff":handoff,"common_recovery":common,"terminal":terminal}

static func _contact(role: String, actions: Dictionary, ctx: Dictionary, patterns: Dictionary) -> Dictionary:
	var target: String = opponent(role)
	var action: Dictionary = actions[role]
	var victim: Dictionary = actions[target]
	var card: Dictionary = action.card
	var kind := "hit"
	var frame := int(action.start)
	var active: bool = _defense_active(victim,frame)
	if not _reachable(card,int(ctx.distance)):
		kind = "whiff"
	elif active and victim.card.defense == "dodge" and not card.ignore_defenses.has("dodge"):
		kind = "dodged"
	elif active and victim.card.defense == "parry" and card.range == "melee" and not card.ignore_defenses.has("parry"):
		kind = "parried"
	elif active and victim.card.defense == "block" and not card.ignore_defenses.has("block"):
		kind = "blocked"
	elif frame<=int(victim.wait):
		kind = "punish"
	elif bool(victim.card.attack) and not victim.ready and frame>int(victim.wait):
		kind = "counter"
	action.punish = kind=="punish"
	var parts: Array = []
	var raw := 0.0
	if kind not in ["whiff","dodged","parried"]:
		raw = _damage(action,ctx[role],patterns[role],kind,parts)
	var rolled := maxi(1,int(round(raw))) if raw > 0.0 else 0
	var damage := mini(rolled,int(ctx[target].hp))
	var armor: bool = not victim.ready and frame>int(victim.wait) and int(victim.card.stun_guard)>int(card.impact) and not bool(card.breaks_armor)
	var interrupt: bool = damage > 0 and not victim.ready and not armor
	return {"source":role,"target":target,"card_id":action.id,"clip":action.clip,"kind":kind,"frame":frame,"distance":int(ctx.distance),"damage":damage,"rolled_damage":rolled,"raw_damage":raw,"parts":parts,"interrupt":interrupt,"armor":armor,"impact":int(card.impact),"before_hp":int(ctx[target].hp)}

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
