extends RefCounted
## Pure public-information forecasts. Instances own immutable worker snapshots.
const Defs = preload("res://scripts/tactical_defs.gd")
const Rules = preload("res://scripts/tactical_rules.gd")
const STATE_KEYS := ["hp","rage","jokers","ready_delay","focus","dodge_charge","tempo"]
const LABELS := {"hit":"可命中","counter":"可打康","punish":"可确反","blocked":"会被挡","dodged":"会被闪","parried":"会被架","whiff":"距离风险","interrupted":"会被打断","guarded":"可格挡","evaded":"可闪避","parry_success":"可招架","setup":"可完成","skipped":"未执行"}
var player_plan: Array = []
var enemy_preview: Array = []
var context: Dictionary = {}
var input_key := ""
var generation := 0
var output: Dictionary = {}

func _init(plan: Array = [],preview: Array = [],public_context: Dictionary = {},key: String = "",version: int = 0) -> void:
	player_plan = plan.duplicate()
	enemy_preview = preview.duplicate()
	context = public_snapshot(public_context)
	input_key = key
	generation = version

func run_job() -> void:
	output = forecast_plan(player_plan,enemy_preview,context)

static func public_snapshot(source: Dictionary) -> Dictionary:
	var ctx: Dictionary = Rules.default_context()
	for key in ["round_id","turn","distance"]:
		if source.has(key):
			ctx[key] = source[key]
	ctx.action_count = Defs.PLAY
	for role in Rules.ROLES:
		var fighter = source.get(role,{})
		if not fighter is Dictionary:
			return {}
		for key in STATE_KEYS:
			if fighter.has(key):
				var value = fighter[key]
				ctx[role][key] = value.duplicate(true) if value is Array or value is Dictionary else value
		if not ctx[role].jokers is Array:
			return {}
	return ctx

static func cache_key(plan: Array,preview: Array,source: Dictionary) -> String:
	return JSON.stringify([plan,preview,public_snapshot(source)])

static func _error() -> Dictionary:
	return {"error":"Invalid public forecast input","beats":[],"sample_count":0}

static func _fill(plan: Array,index: int,counts: Dictionary,out: Array) -> void:
	if index==plan.size():
		out.append(plan.duplicate())
		return
	if plan[index]!=null:
		_fill(plan,index+1,counts,out)
		return
	for id in Defs.CARD_IDS:
		if int(counts.get(id,0))>=2:
			continue
		plan[index] = id
		counts[id] = int(counts.get(id,0))+1
		_fill(plan,index+1,counts,out)
		counts[id] -= 1
		plan[index] = null

static func _player_outcome(beat: Dictionary) -> Dictionary:
	var action: Dictionary = beat.actions.player
	var kind := "interrupted" if action.cancelled else "setup"
	var damage := 0
	for group in beat.groups:
		for hit in group.hits:
			if hit.source=="player":
				kind = String(hit.kind)
				damage += int(hit.damage)
			elif not action.card.attack:
				if hit.kind=="blocked":
					kind = "guarded"
				elif hit.kind=="dodged":
					kind = "evaded"
				elif hit.kind=="parried":
					kind = "parry_success"
	return {"kind":kind,"damage":damage}

static func forecast_plan(plan: Array,preview: Array,source: Dictionary) -> Dictionary:
	if plan.size()!=Defs.PLAY or preview.size()!=Defs.PLAY or preview.count(null)>Defs.ENEMY_HIDDEN:
		return _error()
	for id in plan:
		if not Defs.CARD_IDS.has(String(id)):
			return _error()
	var counts := {}
	for id in preview:
		if id==null:
			continue
		if not Defs.CARD_IDS.has(String(id)):
			return _error()
		counts[id] = int(counts.get(id,0))+1
		if int(counts[id])>2:
			return _error()
	var ctx: Dictionary = public_snapshot(source)
	if ctx.is_empty():
		return _error()
	var possible: Array = []
	_fill(preview.duplicate(),0,counts,possible)
	if possible.is_empty():
		return _error()
	var rows: Array = []
	for index in range(Defs.PLAY):
		rows.append({"beat":index+1,"kinds":[],"damage_min":Defs.HP,"damage_max":0,"distance_min":2,"distance_max":0,"delay_min":Defs.MAX_READY_DELAY,"delay_max":0,"start_min":2147483647,"start_max":0,"window_min":Defs.MAX_READY_DELAY,"window_max":0})
	for enemy_plan in possible:
		var resolved: Dictionary = Rules.resolve_exchange(plan,enemy_plan,ctx)
		if resolved.has("error"):
			return _error()
		for index in range(Defs.PLAY):
			var row: Dictionary = rows[index]
			var outcome := {"kind":"skipped","damage":0}
			var after: Dictionary = resolved.next_state
			if index<resolved.events.size():
				var beat: Dictionary = resolved.events[index]
				outcome = _player_outcome(beat)
				after = beat.after
				row.start_min = mini(int(row.start_min),int(beat.actions.player.start))
				row.start_max = maxi(int(row.start_max),int(beat.actions.player.start))
				row.window_min = mini(int(row.window_min),int(beat.actions.foe.wait))
				row.window_max = maxi(int(row.window_max),int(beat.actions.foe.wait))
			if not row.kinds.has(outcome.kind):
				row.kinds.append(String(outcome.kind))
			row.damage_min = mini(int(row.damage_min),int(outcome.damage))
			row.damage_max = maxi(int(row.damage_max),int(outcome.damage))
			row.distance_min = mini(int(row.distance_min),int(after.distance))
			row.distance_max = maxi(int(row.distance_max),int(after.distance))
			row.delay_min = mini(int(row.delay_min),int(after.player.ready_delay))
			row.delay_max = maxi(int(row.delay_max),int(after.player.ready_delay))
	for row in rows:
		if int(row.start_min)==2147483647:
			row.start_min = 0
			row.window_min = 0
		row.kinds.sort()
		row["certain"] = row.kinds.size()==1
		row["label"] = LABELS.get(String(row.kinds[0]),"结果未定") if row.certain else ("可能中断" if row.kinds.has("skipped") else ("距离风险" if row.kinds.has("whiff") else "结果未定"))
	return {"beats":rows,"sample_count":possible.size()}
