extends RefCounted
## Owns physical cards, decisions, and exactly-once presentation-time state.
const Defs = preload("res://scripts/tactical_defs.gd")
const Rules = preload("res://scripts/tactical_rules.gd")
const AI = preload("res://scripts/tactical_ai.gd")
const Forecast = preload("res://scripts/tactical_forecast.gd")
const START_S := 0.28
const FRAME_S := 0.04
const RECOVER_S := 0.46
const HOLD_S := 0.10

signal beat_started(beat: Dictionary)
signal contact_group(group: Dictionary)
signal round_started(round_id: int)
signal phase_changed(phase: String)

var phase := "loadout"
var phase_time := 0.0
var state: Dictionary = Rules.default_context()
var hand: Array = []
var enemy_hand: Array = []
var offers: Array = []
var enemy_offers: Array = []
var selected: Array = []
var player_plan: Array = []
var enemy_plan: Array = []
var enemy_preview: Array = []
var swaps_used := 0
var enemy_hint := ""
var patterns: Dictionary = {}
var round_index := 1
var turn_index := 1
var wins: Array = [0,0]
var round_winner := ""
var match_winner := ""
var notice := "选择三项天赋，按选择顺序触发"
var paused := false
var bot := false
var seed_value := 1
var result: Dictionary = {}
var resolution_time := 0.0
var active_beat: Dictionary = {}
var active_beat_start := 0.0
var latest_hits: Array = []
var combat_log: Array = []
var action_feedback := {"player":[],"foe":[]}
var last_exchange_feedback: Dictionary = {}
var feedback_revision := 0
var audit: Array = []
var history: Array = []
var forecast: Dictionary = {}
var forecast_status := "idle"
var forecast_revision := 0
var plan_revision := 0
var _forecast_generation := 0
var _forecast_task := -1
var _forecast_job = null
var _forecast_key := ""
var _forecast_pending: Dictionary = {}
var _forecast_cache: Dictionary = {}
var _forecast_cache_order: Array = []
var _enemy_indices: Array = []
var _enemy_plan: Array = []
var _decks := {"player":[],"foe":[]}
var _discards := {"player":[],"foe":[]}
var _randoms: Dictionary = {}
var _schedule: Array = []
var _schedule_index := 0
var _applied: Dictionary = {}
var _serial := 0

func _init(initial_seed: int = 0) -> void:
	restart(initial_seed)

func restart(initial_seed: int = 0) -> void:
	_invalidate_forecast()
	_forecast_cache.clear()
	_forecast_cache_order.clear()
	_serial += 1
	seed_value = initial_seed if initial_seed != 0 else int(Time.get_ticks_usec())
	_randoms.clear()
	for role in ["player","foe","draft","veil"]:
		var random := RandomNumberGenerator.new()
		random.seed = seed_value+{"player":0,"foe":200003,"draft":900005,"veil":700007}[role]
		_randoms[role] = random
	state = Rules.default_context()
	offers = _shuffle(Defs.joker_ids(),"draft").slice(0,6)
	enemy_offers = _shuffle(Defs.joker_ids(),"draft").slice(0,6)
	state.foe.jokers = AI.choose_loadout(enemy_offers,seed_value)
	selected.clear()
	player_plan.clear()
	enemy_plan.clear()
	enemy_preview.clear()
	swaps_used = 0
	_enemy_plan.clear()
	_enemy_indices.clear()
	hand.clear()
	enemy_hand.clear()
	_decks = {"player":[],"foe":[]}
	_discards = {"player":[],"foe":[]}
	wins = [0,0]
	round_index = 1
	turn_index = 1
	round_winner = ""
	match_winner = ""
	enemy_hint = ""
	patterns.clear()
	result.clear()
	active_beat.clear()
	_schedule.clear()
	_applied.clear()
	_schedule_index = 0
	resolution_time = 0.0
	latest_hits.clear()
	combat_log.clear()
	_reset_action_feedback()
	last_exchange_feedback.clear()
	audit.clear()
	history.clear()
	paused = false
	_set_phase("loadout","选择三项天赋，按选择顺序触发")

func _shuffle(values: Array, role: String) -> Array:
	var out: Array = values.duplicate()
	for i in range(out.size()-1,0,-1):
		var j: int = _randoms[role].randi_range(0,i)
		var swap = out[i]
		out[i] = out[j]
		out[j] = swap
	return out

func _set_phase(next_phase: String, message: String = "") -> void:
	_invalidate_forecast()
	phase = next_phase
	phase_time = 0.0
	if message != "":
		notice = message
	phase_changed.emit(phase)

func toggle(index: int) -> bool:
	if paused or phase not in ["loadout","select"]:
		return false
	var count := offers.size() if phase == "loadout" else hand.size()
	if index < 0 or index >= count or (phase != "loadout" and hand[index] == null):
		return false
	if selected.has(index):
		selected.erase(index)
		_invalidate_forecast()
		return true
	var limit := Defs.JOKER_SLOTS if phase == "loadout" else Defs.PLAY
	if selected.size() >= limit:
		notice = "最多选%d项天赋；再次点击可取消" % limit if phase == "loadout" else "最多选%d张动作牌；再次点击可取消" % limit
		return false
	selected.append(index)
	_invalidate_forecast()
	return true

func undo() -> void:
	if not paused and not selected.is_empty() and phase in ["loadout","select"]:
		selected.pop_back()
		_invalidate_forecast()

func move_selected(from: int, to: int) -> bool:
	if paused or bot or phase!="select" or from<0 or to<0 or from>=selected.size() or to>=selected.size() or from==to:
		return false
	var physical_index: int = selected.pop_at(from)
	selected.insert(to,physical_index)
	_invalidate_forecast()
	return true

func swap_card(index: int) -> bool:
	if paused or phase != "select" or swaps_used >= Defs.DISCARD_MAX or index < 0 or index >= hand.size() or hand[index] == null:
		return false
	_swap_cards("player",[index])
	selected.erase(index)
	_invalidate_forecast()
	swaps_used += 1
	notice = "已换 %d/%d 张 · 按顺序编排五张牌" % [swaps_used,Defs.DISCARD_MAX]
	return true

func confirm() -> bool:
	if paused:
		return false
	match phase:
		"loadout":
			if selected.size() != Defs.JOKER_SLOTS:
				notice = "请选择三项天赋"
				return false
			state.player.jokers = selected.map(func(index): return offers[index])
			selected.clear()
			_new_round()
		"select":
			if selected.size() != Defs.PLAY:
				notice = "请按顺序选满%d张动作牌" % Defs.PLAY
				return false
			player_plan = selected.map(func(index): return hand[index])
			enemy_plan = _enemy_plan.duplicate()
			enemy_preview = enemy_plan.duplicate()
			patterns = {"player":_preview_pattern(player_plan,"player"),"foe":_preview_pattern(enemy_plan,"foe")}
			_spend_cards("player",selected)
			_spend_cards("foe",_enemy_indices)
			selected.clear()
			_set_phase("reveal","亮牌：攻防决定命中，牌型强化收益")
		_:
			return false
	return true

func _prepare_exchange() -> void:
	_reset_action_feedback()
	selected.clear()
	player_plan.clear()
	enemy_plan.clear()
	patterns.clear()
	swaps_used = 0
	# Enemy commitment and visibility are complete before planning input is enabled.
	_swap_cards("foe",AI.choose_discards(enemy_hand,public_context("foe"),"foe"))
	_enemy_indices = AI.choose_plan(enemy_hand,public_context("foe"),"foe")
	_enemy_plan = _enemy_indices.map(func(index): return enemy_hand[index])
	assert(_enemy_plan.size() == Defs.PLAY)
	enemy_preview = _enemy_plan.duplicate()
	var positions: Array = []
	for index in range(Defs.PLAY):
		positions.append(index)
	for index in _shuffle(positions,"veil").slice(0,Defs.ENEMY_HIDDEN):
		enemy_preview[index] = null
	enemy_hint = "%d明牌 · %d暗牌" % [Defs.PLAY-Defs.ENEMY_HIDDEN,Defs.ENEMY_HIDDEN]
	_set_phase("select","读敌方三张明牌，再按顺序编排五张；换牌可选")

func _preview_pattern(plan: Array, role: String) -> Dictionary:
	var pattern: Dictionary = Defs.evaluate(plan)
	if float(state[role].rage) >= 100.0:
		pattern.flat += 1
		pattern.mult += 0.1
		pattern.ex = true
	return pattern

func _new_round() -> void:
	var previous: Dictionary = state.duplicate(true)
	state = Rules.default_context()
	state.round_id = _serial*10+round_index
	state.turn = 1
	for role in ["player","foe"]:
		state[role].jokers = previous[role].jokers.duplicate()
		state[role].rage = float(previous[role].rage)
		_decks[role] = _shuffle(Defs.deck(),role)
		_discards[role] = []
	hand = []
	enemy_hand = []
	for role in ["player","foe"]:
		_refill(role,Defs.HAND)
		_ensure_opener(role)
	turn_index = 1
	selected.clear()
	player_plan.clear()
	enemy_plan.clear()
	enemy_preview.clear()
	swaps_used = 0
	_enemy_plan.clear()
	enemy_hint = ""
	patterns.clear()
	result.clear()
	active_beat.clear()
	latest_hits.clear()
	combat_log.clear()
	_reset_action_feedback()
	last_exchange_feedback.clear()
	_set_phase("intro","第 %d 局 · 准备交锋" % round_index)
	round_started.emit(int(state.round_id))

func _cards(role: String) -> Array:
	return hand if role == "player" else enemy_hand

func _draw(role: String) -> String:
	if _decks[role].is_empty():
		_decks[role] = _shuffle(_discards[role],role)
		_discards[role] = []
	assert(not _decks[role].is_empty(),"Finite deck must contain a drawable card")
	return String(_decks[role].pop_back())

func _refill(role: String, target_size: int) -> void:
	var kept: Array = _cards(role).filter(func(id): return id != null)
	while kept.size() < target_size:
		kept.append(_draw(role))
	if role == "player":
		hand = kept
	else:
		enemy_hand = kept

func _ensure_opener(role: String) -> void:
	var cards: Array = _cards(role)
	for pass_index in range(3):
		var attacks := 0
		var guards := 0
		for id in cards:
			attacks += 1 if Defs.card(id).attack else 0
			guards += 1 if Defs.card(id).kind == "guard" else 0
		var need := "attack" if attacks < 2 else ("guard" if guards < 1 else "")
		if need == "":
			return
		for source_index in range(_decks[role].size()):
			if Defs.card(_decks[role][source_index]).kind != need:
				continue
			for slot in range(cards.size()):
				var card: Dictionary = Defs.card(cards[slot])
				if card.kind == need or (need == "attack" and card.kind == "guard" and guards == 1) or (need == "guard" and card.attack and attacks == 2):
					continue
				var replaced = cards[slot]
				cards[slot] = _decks[role][source_index]
				_decks[role][source_index] = replaced
				break
			break

func _swap_cards(role: String, indices: Array) -> void:
	assert(indices.size() <= Defs.DISCARD_MAX)
	var cards: Array = _cards(role)
	for index in indices:
		_discards[role].append(cards[index])
		cards[index] = _draw(role)

func _spend_cards(role: String, indices: Array) -> void:
	var cards: Array = _cards(role)
	for index in indices:
		_discards[role].append(cards[index])
		cards[index] = null

func deck_cards(role: String) -> Array:
	var out: Array = _cards(role).filter(func(id): return id != null)
	out.append_array(_decks[role])
	out.append_array(_discards[role])
	return out

func deck_counts(role: String) -> Dictionary:
	return {"draw":_decks[role].size(),"discard":_discards[role].size()}

func public_context(role: String) -> Dictionary:
	var out: Dictionary = state.duplicate(true)
	out["history"] = history.slice(maxi(0,history.size()-3)).duplicate(true)
	out["decision_seed"] = seed_value+round_index*101+turn_index*17+(1000 if role == "foe" else 0)
	if role == "player" and phase == "select":
		out["opponent_preview"] = enemy_preview.duplicate()
	return out

func _invalidate_forecast() -> void:
	plan_revision += 1
	_forecast_generation += 1
	forecast_revision += 1
	_forecast_key = ""
	_forecast_pending = {}
	forecast = {}
	forecast_status = "idle"

func _publish_forecast(output: Dictionary) -> void:
	if output.has("error") or not output.has("beats") or not output.has("sample_count"):
		forecast = {}
		forecast_status = "error"
	else:
		forecast = output.duplicate(true)
		forecast_status = "ready"
	forecast_revision += 1

func _poll_forecast() -> void:
	if _forecast_task<0 or not WorkerThreadPool.is_task_completed(_forecast_task):
		return
	# Completion is the barrier: the worker never writes a live Match or UI node.
	WorkerThreadPool.wait_for_task_completion(_forecast_task)
	var finished = _forecast_job
	_forecast_job = null
	_forecast_task = -1
	if not finished.output.has("error") and finished.output.has("sample_count"):
		if not _forecast_cache.has(finished.input_key):
			_forecast_cache_order.append(finished.input_key)
		_forecast_cache[finished.input_key] = finished.output
		while _forecast_cache_order.size()>16:
			_forecast_cache.erase(_forecast_cache_order.pop_front())
	if finished.generation==_forecast_generation and finished.input_key==_forecast_key and phase=="select" and selected.size()==Defs.PLAY:
		_publish_forecast(finished.output)

func request_forecast() -> void:
	_poll_forecast()
	if phase!="select" or bot or selected.size()!=Defs.PLAY:
		if forecast_status!="idle" or _forecast_key!="" or not _forecast_pending.is_empty():
			_invalidate_forecast()
		return
	var plan: Array = selected.map(func(index): return hand[index])
	var public: Dictionary = Forecast.public_snapshot(public_context("player"))
	var key := Forecast.cache_key(plan,enemy_preview,public)
	if key!=_forecast_key:
		_forecast_generation += 1
		forecast_revision += 1
		_forecast_key = key
		forecast = {}
		forecast_status = "pending"
		_forecast_pending = {"plan":plan,"preview":enemy_preview.duplicate(),"context":public,"key":key,"generation":_forecast_generation}
	if _forecast_cache.has(key):
		if forecast_status!="ready":
			_publish_forecast(_forecast_cache[key])
		_forecast_pending = {}
	elif _forecast_task<0 and not _forecast_pending.is_empty():
		var pending: Dictionary = _forecast_pending
		_forecast_pending = {}
		_forecast_job = Forecast.new(pending.plan,pending.preview,pending.context,pending.key,pending.generation)
		_forecast_task = WorkerThreadPool.add_task(_forecast_job.run_job)

func tick(delta: float) -> void:
	if delta<0.0:
		return
	request_forecast()
	if paused:
		return
	phase_time += delta
	if bot and phase in ["loadout","select"] and phase_time >= 0.25:
		if phase == "loadout":
			selected = AI.choose_loadout(offers,seed_value+1).map(func(id): return offers.find(id))
		else:
			selected = AI.choose_plan(hand,public_context("player"),"player")
		confirm()
		return
	match phase:
		"intro":
			if phase_time >= 1.0:
				_prepare_exchange()
		"reveal":
			if phase_time >= 1.0:
				_begin_resolve()
		"resolve":
			_advance_schedule(resolution_time+delta)
		"round_over":
			if phase_time >= 1.4:
				if int(wins[0]) >= 2 or int(wins[1]) >= 2 or round_index >= Defs.ROUNDS:
					match_winner = "player" if int(wins[0])>int(wins[1]) else ("foe" if int(wins[1])>int(wins[0]) else "draw")
					_set_phase("match_over","你赢了" if match_winner == "player" else ("青岚获胜" if match_winner == "foe" else "整场平局"))
				else:
					round_index += 1
					_new_round()

func _begin_resolve() -> void:
	result = Rules.resolve_exchange(player_plan,enemy_plan,state)
	assert(not result.has("error"),String(result.get("error","")))
	_reset_action_feedback()
	patterns = result.patterns.duplicate(true)
	state.player.rage = 0.0 if patterns.player.ex else state.player.rage
	state.foe.rage = 0.0 if patterns.foe.ex else state.foe.rage
	_schedule.clear()
	_schedule_index = 0
	resolution_time = 0.0
	var at := 0.0
	for raw_beat in result.events:
		var beat: Dictionary = raw_beat.duplicate(true)
		beat["pauses"] = []
		beat["contacts"] = []
		var accumulated_hold := 0.0
		_schedule.append({"at":at,"kind":"beat","beat":beat})
		for raw_group in beat.groups:
			var group: Dictionary = raw_group.duplicate(true)
			var visual_at := START_S+float(group.frame)*FRAME_S
			var local_at := visual_at+accumulated_hold
			group["event_id"] = "%s:%d" % [String(beat.event_id),int(group.frame)]
			group["visual_at"] = visual_at
			_schedule.append({"at":at+local_at,"kind":"contact","group":group})
			beat.contacts.append({"at":visual_at,"group":group})
			if not group.hits.is_empty():
				beat.pauses.append({"at":local_at,"duration":HOLD_S,"visual_at":visual_at})
				accumulated_hold += HOLD_S
		# Only common recovery is consumed here. The remaining difference belongs
		# to the next action's wait; playing both full recoveries would count it twice.
		beat["duration"] = START_S+float(int(beat.handoff)+int(beat.common_recovery))*FRAME_S+(0.45 if beat.terminal else 0.0)
		at += float(beat.duration)+accumulated_hold
		_schedule.append({"at":at,"kind":"beat_end","state":beat.after})
		at += 0.10
	_schedule.append({"at":at,"kind":"finish"})
	_set_phase("resolve","逐拍交锋")
	_advance_schedule(0.0)

func _advance_schedule(to_time: float) -> void:
	while phase == "resolve" and _schedule_index < _schedule.size() and float(_schedule[_schedule_index].at) <= to_time+0.00000001:
		var entry: Dictionary = _schedule[_schedule_index]
		_schedule_index += 1
		resolution_time = float(entry.at)
		match String(entry.kind):
			"beat":
				active_beat = entry.beat
				active_beat_start = resolution_time
				latest_hits.clear()
				beat_started.emit(active_beat.duplicate(true))
			"contact":
				var group: Dictionary = entry.group
				if not _applied.has(group.event_id):
					_applied[group.event_id] = true
					state = group.state.duplicate(true)
					latest_hits = group.hits.duplicate(true)
					_record_action_feedback(group)
					for hit in latest_hits:
						var label := "你" if hit.source == "player" else "青岚"
						combat_log.append("%s · %s · %s%s" % [label,Defs.card(hit.card_id).name,_source_outcome_label(hit.kind)," %d" % int(hit.damage) if int(hit.damage)>0 else ""])
						audit.append(hit.duplicate(true))
					while combat_log.size() > 4:
						combat_log.pop_front()
					contact_group.emit(group.duplicate(true))
			"beat_end":
				state = entry.state.duplicate(true)
			"finish":
				_finish_exchange()
	if phase == "resolve":
		resolution_time = to_time

func _reset_action_feedback() -> void:
	for role in ["player","foe"]:
		action_feedback[role] = []
		for index in range(Defs.PLAY):
			action_feedback[role].append({})
	feedback_revision += 1

func feedback_for(role: String,index: int) -> Dictionary:
	var rows: Array = action_feedback.get(role,[])
	return rows[index].duplicate(true) if index>=0 and index<rows.size() else {}

static func _source_outcome_label(kind: String) -> String:
	return {"blocked":"被格挡","dodged":"被闪避","parried":"被招架"}.get(kind,Defs.outcome_label(kind))

func _record_action_feedback(group: Dictionary) -> void:
	var index := int(active_beat.beat)-1
	for change in group.changes:
		action_feedback[change.role][index] = {"kind":"setup","label":"完成","reason":"","damage":0,"taken":0,"parts":[]}
	for hit in group.hits:
		var source: String = hit.source
		var target: String = hit.target
		var attacker: Dictionary = active_beat.actions[source]
		var victim: Dictionary = active_beat.actions[target]
		var kind: String = hit.kind
		var reason := ""
		if kind=="whiff":
			reason = "当时%s，需要%s" % [Defs.distance_label(int(hit.distance)),Defs.range_label(attacker.card)]
		elif kind=="dodged":
			reason = "对手的闪避窗口仍有效"
		elif kind=="parried":
			reason = "对手的招架窗口仍有效"
		action_feedback[source][index] = {"kind":kind,"label":_source_outcome_label(kind),"reason":reason,"damage":int(hit.damage),"taken":0,"parts":hit.parts.duplicate(true)}
		var defense_name: String = {"block":"格挡","dodge":"闪避","parry":"招架"}.get(victim.card.defense,"")
		var defended := {"kind":"","label":"","reason":"","damage":0,"taken":int(hit.damage),"parts":[]}
		if hit.interrupt:
			defended.kind = "interrupted"
			defended.label = "被打断"
			defended.reason = "对手第%d帧命中，你原定第%d帧出手" % [hit.frame,victim.start]
		elif kind in ["blocked","dodged","parried"]:
			defended.kind = {"blocked":"guarded","dodged":"evaded","parried":"parry_success"}[kind]
			defended.label = defense_name+"成功"
			defended.reason = "伤害减少80%" if kind=="blocked" else "避开%s，对手收招%d帧" % [attacker.card.name,int(attacker.ready_at)-int(hit.frame)]
		elif int(hit.damage)>0 and defense_name!="":
			var window := int(victim.card.get("defense_window",0))
			if attacker.card.ignore_defenses.has(victim.card.defense) or (victim.card.defense=="parry" and attacker.card.range!="melee"):
				defended.kind = "defense_bypassed"
				defended.label = "防御无效"
				defended.reason = "%s无法用%s挡住" % [attacker.card.name,defense_name]
			elif window>0 and int(hit.frame)>=int(victim.start)+window:
				defended.kind = "defense_expired"
				defended.label = defense_name+"过早"
				defended.reason = "攻击第%d帧命中，%s窗口%d–%d帧" % [hit.frame,defense_name,victim.start,int(victim.start)+window-1]
		if defended.kind!="":
			action_feedback[target][index] = defended
	feedback_revision += 1

func last_exchange_summary() -> String:
	if last_exchange_feedback.is_empty():
		return ""
	var outcomes: Array = []
	var rows: Array = last_exchange_feedback.feedback.player
	for index in range(rows.size()):
		outcomes.append(str(index+1)+String(rows[index].label))
	return "上轮 造成%d / 受伤%d · %s" % [last_exchange_feedback.dealt,last_exchange_feedback.taken," ".join(PackedStringArray(outcomes))]

func last_exchange_details() -> Dictionary:
	# Completed playback only: no simulation, live plan or hidden-card lookup.
	return last_exchange_feedback.duplicate(true)

func visual_time() -> float:
	if active_beat.is_empty():
		return 0.0
	var local := maxf(0.0,resolution_time-active_beat_start)
	var removed := 0.0
	for pause in active_beat.pauses:
		if local < float(pause.at):
			break
		removed += minf(float(pause.duration),local-float(pause.at))
	return minf(float(active_beat.duration),local-removed)

func visual_frozen() -> bool:
	if paused:
		return true
	var local := resolution_time-active_beat_start
	for pause in active_beat.get("pauses",[]):
		if local >= float(pause.at) and local < float(pause.at)+float(pause.duration):
			return true
	return false

func _finish_exchange() -> void:
	state = result.next_state.duplicate(true)
	var completed: Dictionary = action_feedback.duplicate(true)
	var dealt := 0
	var taken := 0
	for role in ["player","foe"]:
		for index in range(Defs.PLAY):
			if completed[role][index].is_empty():
				completed[role][index] = {"kind":"skipped","label":"未执行","reason":"交锋已结束","damage":0,"taken":0,"parts":[]}
			if role=="player":
				dealt += int(completed[role][index].damage)
			else:
				taken += int(completed[role][index].damage)
	action_feedback = completed.duplicate(true)
	last_exchange_feedback = {"round":round_index,"turn":turn_index,"feedback":completed,"plans":{"player":player_plan.duplicate(),"foe":enemy_plan.duplicate()},"dealt":dealt,"taken":taken}
	feedback_revision += 1
	history.append({"player":player_plan.duplicate(),"foe":enemy_plan.duplicate()})
	if history.size()>3:
		history.pop_front()
	active_beat.clear()
	_schedule.clear()
	if int(state.player.hp) <= 0 or int(state.foe.hp) <= 0 or turn_index >= Defs.TURNS:
		round_winner = "player" if int(state.player.hp)>int(state.foe.hp) else ("foe" if int(state.foe.hp)>int(state.player.hp) else "draw")
		if round_winner != "draw":
			wins[0 if round_winner == "player" else 1] += 1
		var reason := "双 K.O." if int(state.player.hp)==0 and int(state.foe.hp)==0 else ("K.O." if int(state.player.hp)==0 or int(state.foe.hp)==0 else "六轮战罢")
		_set_phase("round_over",reason+" · "+("你拿下一局" if round_winner == "player" else ("青岚拿下一局" if round_winner == "foe" else "本局平手")))
		return
	for role in ["player","foe"]:
		var target := mini(Defs.HAND_MAX,Defs.HAND+int(state[role].extra_draw))
		_refill(role,target)
		state[role].extra_draw = 0
	turn_index += 1
	state.turn = turn_index
	selected.clear()
	_enemy_plan.clear()
	_enemy_indices.clear()
	enemy_hint = ""
	_prepare_exchange()

func signature() -> String:
	var animated: bool = phase in ["intro","reveal","resolve","round_over"]
	return str([phase,phase_time if animated else 0.0,paused,state,hand,selected,offers,player_plan,enemy_plan,enemy_preview,swaps_used,enemy_hint,patterns,wins,round_index,turn_index,notice,latest_hits,combat_log,forecast_revision,forecast_status,feedback_revision])
