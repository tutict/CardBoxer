extends RefCounted
## Tactical-only catalog. The realtime card/animation contract remains unchanged.
const Base = preload("res://scripts/card_data.gd")
const HAND := 8
const HAND_MAX := 10
const PLAY := 5
const JOKER_SLOTS := 3
const ENEMY_HIDDEN := 2
const DISCARD_MAX := 3
const TURNS := 6
const ROUNDS := 3
const HP := 100
const MAX_READY_DELAY := 12
const COMBO_BUDGET := 4
const COMBO_SPEED := 2
const CARD_IDS := ["jab","cross","uppercut","sweep","wave","throw","rush","backstep","guard","sidestep","focus","recover","feint","parry","delayed_heavy","guard_break","armored_heavy","pursuit"]
const JOKER_IDS := ["shadow","opening","counter","pressure","wind","sequence","triple","breaker"]
const NEW_CARDS := {
	"feint": {"rank":1,"name":"佯攻","tag":"骗","kind":"move","windup":4,"damage":0,"clip":"jab"},
	"parry": {"rank":2,"name":"招架","tag":"架","kind":"guard","windup":2,"damage":0,"clip":"guard"},
	"delayed_heavy": {"rank":3,"name":"延迟重拳","tag":"迟","kind":"attack","windup":12,"damage":9,"clip":"cross"},
	"guard_break": {"rank":4,"name":"破防击","tag":"破","kind":"attack","windup":9,"damage":8,"clip":"cross"},
	"armored_heavy": {"rank":6,"name":"霸体重拳","tag":"霸","kind":"attack","windup":10,"damage":10,"clip":"uppercut"},
	"pursuit": {"rank":7,"name":"追击拳","tag":"追","kind":"attack","windup":6,"damage":5,"clip":"jab"},
}
## Tactical values are independent of the realtime animation/card parameters.
const TIMING := {
	"jab":{"windup":4,"damage":4,"range_min":0,"range_max":1,"recover":6,"whiff_recover":8,"hitstun":9,"blockstun":6,"impact":2,"stun_guard":0,"combo_role":"starter","combo_cost":1,"ai_style":"pressure"},
	"cross":{"windup":6,"damage":6,"range_min":0,"range_max":1,"recover":8,"whiff_recover":11,"hitstun":10,"blockstun":5,"impact":3,"stun_guard":0,"combo_role":"starter_linker","combo_cost":1,"ai_style":"pressure"},
	"uppercut":{"windup":8,"damage":10,"range_min":0,"range_max":0,"recover":13,"whiff_recover":19,"hitstun":17,"blockstun":5,"impact":6,"stun_guard":0,"combo_role":"ender","combo_cost":2,"ai_style":"heavy"},
	"sweep":{"windup":8,"damage":6,"range_min":1,"range_max":1,"recover":10,"whiff_recover":14,"hitstun":14,"blockstun":5,"impact":4,"stun_guard":3,"combo_role":"starter","combo_cost":1,"ai_style":"pressure"},
	"wave":{"windup":10,"damage":9,"range_min":1,"range_max":2,"recover":14,"whiff_recover":20,"hitstun":10,"blockstun":7,"impact":3,"stun_guard":0,"combo_role":"standalone","combo_cost":0,"ai_style":"ranged"},
	"throw":{"windup":5,"damage":8,"range_min":0,"range_max":0,"recover":11,"whiff_recover":16,"hitstun":12,"blockstun":0,"impact":4,"stun_guard":0,"combo_role":"standalone","combo_cost":0,"ai_style":"breaker"},
	"pursuit":{"windup":6,"damage":5,"range_min":0,"range_max":1,"recover":7,"whiff_recover":11,"hitstun":9,"blockstun":4,"impact":3,"stun_guard":0,"combo_role":"linker","combo_cost":1,"ai_style":"pressure"},
	"guard_break":{"windup":9,"damage":8,"range_min":0,"range_max":1,"recover":12,"whiff_recover":17,"hitstun":12,"blockstun":0,"impact":5,"stun_guard":0,"combo_role":"ender","combo_cost":2,"ai_style":"breaker"},
	"delayed_heavy":{"windup":12,"damage":9,"range_min":0,"range_max":1,"recover":13,"whiff_recover":18,"hitstun":15,"blockstun":8,"impact":5,"stun_guard":0,"combo_role":"standalone","combo_cost":0,"ai_style":"heavy"},
	"armored_heavy":{"windup":10,"damage":10,"range_min":0,"range_max":1,"recover":14,"whiff_recover":20,"hitstun":15,"blockstun":6,"impact":6,"stun_guard":5,"combo_role":"standalone","combo_cost":0,"ai_style":"heavy"},
	"rush":{"windup":4,"recover":4,"ai_style":"advance"},
	"backstep":{"windup":3,"recover":5,"ai_style":"retreat"},
	"guard":{"windup":2,"recover":0,"ai_style":"defense"},
	"sidestep":{"windup":2,"recover":6,"ai_style":"defense"},
	"parry":{"windup":2,"recover":8,"ai_style":"defense"},
	"feint":{"windup":4,"recover":5,"range_min":0,"range_max":1,"ai_style":"setup"},
	"focus":{"windup":10,"recover":6,"ai_style":"setup"},
	"recover":{"windup":4,"recover":3,"ai_style":"setup"},
}
## Mechanics live beside their definitions. The resolver never switches on card IDs.
const CARD_RULES := {
	"cross":{"damage_effects":[{"when":"counter","name":"交叉反击","op":"+","value":3}]},
	"sweep":{"hit_distance":1},
	"wave":{"range":"projectile"},
	"throw":{"range":"throw","ignore_defenses":["block","parry"],"breaks_armor":true,"tags":["throw","break_guard"]},
	"rush":{"on_ready":[{"op":"distance","value":-1}],"tags":["advance"]},
	"backstep":{"on_ready":[{"op":"distance","value":1}],"tags":["retreat"]},
	"guard":{"defense":"block","block_draw":1},
	"sidestep":{"defense":"dodge","defense_window":9},
	"focus":{"on_ready":[{"op":"set","stat":"focus","value":true}],"tags":["focus"]},
	"recover":{"on_start":[{"op":"reduce","stat":"ready_delay","value":4}],"on_ready":[{"op":"add","stat":"extra_draw","value":1}]},
	"feint":{"bait_frames":6,"tags":["feint"]},
	"parry":{"defense":"parry","defense_window":9,"parry_recover":4,"parry_penalty":4},
	"guard_break":{"ignore_defenses":["block"],"tags":["break_guard"]},
	"armored_heavy":{"armor":true},
	"pursuit":{"follow":true,"on_ready":[{"op":"distance","value":-1,"when":"follow"}],"damage_effects":[{"when":"follow","name":"追击","op":"+","value":3}]},
}
const JOKER_EFFECTS := {
	"shadow":[{"event":"damage","when":"shadow_ready","op":"+","value":3}],
	"opening":[{"event":"damage","when":"punish","op":"×","value":1.25}],
	"counter":[{"event":"damage","when":"counter","op":"+","value":3}],
	"pressure":[{"event":"attack","kinds":["counter"],"once":true,"state_effects":[{"op":"set","stat":"tempo","value":2}]}],
	"wind":[{"event":"defend","kinds":["dodged","parried"],"once":true,"state_effects":[{"op":"add","stat":"extra_draw","value":1}]}],
	"sequence":[{"event":"damage","when":"pattern_tag","tag":"sequence","op":"×","value":1.25}],
	"triple":[{"event":"damage","when":"pattern_tag","tag":"triple","op":"+","value":2}],
	"breaker":[{"event":"attack","kinds":["hit","counter","punish"],"requires_tag":"break_guard","once":true,"state_effects":[{"op":"add","stat":"extra_draw","value":1}]}],
}
const PATTERNS := {
	"scatter":{"name":"散牌","flat":0,"mult":1.0,"tags":[]},
	"pair":{"name":"一对","flat":1,"mult":1.0,"tags":[]},
	"two_pair":{"name":"两对","flat":2,"mult":1.10,"tags":[]},
	"sequence":{"name":"三连","flat":2,"mult":1.15,"tags":["sequence"]},
	"triple":{"name":"三同","flat":3,"mult":1.25,"tags":["triple"]},
	"straight":{"name":"五连","flat":4,"mult":1.30,"tags":["sequence"]},
	"full_house":{"name":"葫芦","flat":4,"mult":1.35,"tags":["triple"]},
	"four":{"name":"四同","flat":5,"mult":1.45,"tags":["triple"]},
	"five":{"name":"五同","flat":6,"mult":1.60,"tags":["triple"]},
}
const TEXT := {
	"jab":"安全轻击与连段起手。抢中攻击起手时打康；轻打断力压不住抗打断招式。",
	"cross":"交叉反击。打康时再加伤3；也能接闪避确反。",
	"uppercut":"贴身终结。强打断与高爆发，被挡或打空后容易遭确反。",
	"sweep":"中距控场。抵抗轻抢招，命中推远一档；接追击收回距离。",
	"wave":"中远距压制。贴身会打空；起手和收招较长，可被侧闪。",
	"throw":"投技。只打贴身，无视格挡和招架，可打断霸体。",
	"rush":"突进。接近一档，完成前可能被打断。",
	"backstep":"后撤。拉开一档，令近身招打空后再反击。",
	"guard":"格挡。本拍伤害减80%，首次成功下轮多摸1；防不住投技和破防击。",
	"sidestep":"侧闪。九帧窗口躲攻击，以对手打空恢复换先手；下一招须赶上窗口。",
	"focus":"蓄势。下次攻击尝试加伤3；起手中可被打断。",
	"recover":"卸力。起拍减少4帧延迟，仍会受伤；完成后下轮多摸1张。",
	"feint":"佯攻。贴身或中距骗到已激活的防御，制造6帧先手；空骗无收益。",
	"parry":"招架。九帧窗口化解普通近身攻击，成功赚更大反击窗口；防不了投技和波。",
	"delayed_heavy":"延迟重拳。抓过早闪避或招架的窗口尾，容易被快招打断。",
	"guard_break":"破防击。无视格挡，可被侧闪或招架。",
	"armored_heavy":"霸体。起手中抗打断5，伤害照受；强打断与投技可以中断，等待中不生效。",
	"pursuit":"追击连接。接有效连段或赶上确反窗口时，前进一档并加伤3；单出用基础招。",
}
const JOKERS := {
	"shadow": {"name":"掠影","tag":"闪","text":"闪避成功后，下一次攻击尝试加伤3。","color":Color(0.32,0.82,0.78)},
	"opening": {"name":"趁隙","tag":"隙","text":"确反伤害×1.25。排在加伤天赋后，收益更高。","color":Color(0.39,0.70,0.95)},
	"counter": {"name":"抢拍","tag":"康","text":"打康伤害额外+3。","color":Color(0.96,0.51,0.30)},
	"pressure": {"name":"压制","tag":"压","text":"本轮首次打康后，下一拍攻击起手-2，最低1。","color":Color(0.94,0.34,0.42)},
	"wind": {"name":"追风","tag":"摸","text":"本轮首次闪避或招架成功，下轮多摸1张。","color":Color(0.40,0.78,0.59)},
	"sequence": {"name":"顺势","tag":"连","text":"三连或五连牌型，本轮攻击伤害×1.25。","color":Color(0.76,0.58,0.95)},
	"triple": {"name":"三重奏","tag":"同","text":"三同、葫芦、四同或五同，本轮攻击伤害+2。","color":Color(0.98,0.77,0.38)},
	"breaker": {"name":"破阵","tag":"破","text":"本轮首次投技或破防击命中，下轮多摸1张。","color":Color(0.81,0.65,0.41)},
}

static func card_ids() -> Array:
	return CARD_IDS.duplicate()

static func joker_ids() -> Array:
	return JOKER_IDS.duplicate()

static func deck() -> Array:
	var out: Array = []
	for id in CARD_IDS:
		out.append(id)
		out.append(id)
	return out

static func card(id: String) -> Dictionary:
	if not CARD_IDS.has(id):
		return {}
	var data: Dictionary = NEW_CARDS[id].duplicate(true) if NEW_CARDS.has(id) else Base.card(id).duplicate(true)
	data["id"] = id
	data["clip"] = data.get("clip",id)
	data["attack"] = String(data.kind) == "attack"
	data["range"] = "melee"
	data["defense"] = ""
	data["armor"] = false
	data["breaks_armor"] = false
	data["follow"] = false
	data["ignore_defenses"] = []
	data["tags"] = []
	data.merge({"range_min":0,"range_max":2 if not data.attack else 1,"recover":0,"whiff_recover":0,"hitstun":0,"blockstun":0,"impact":0,"stun_guard":0,"combo_role":"none","combo_cost":0,"ai_style":"setup"},true)
	data.merge(TIMING[id],true)
	for key in CARD_RULES.get(id,{}):
		var value = CARD_RULES[id][key]
		data[key] = value.duplicate(true) if value is Array or value is Dictionary else value
	data["armor"] = int(data.stun_guard)>0
	data["text"] = TEXT[id]
	data["speed_label"] = "快" if int(data.windup) <= 6 else ("中" if int(data.windup) <= 9 else "慢")
	data["hint"] = hint_for(id)
	return data

static func hint_for(id: String) -> String:
	var rule: Dictionary = CARD_RULES.get(id,{})
	var tags: Array = rule.get("tags",[])
	if rule.get("defense","") in ["block","parry"]:
		return "守势"
	if rule.get("defense","") == "dodge" or tags.has("retreat"):
		return "闪避"
	if tags.has("advance") or tags.has("feint"):
		return "进逼"
	var data: Dictionary = NEW_CARDS[id] if NEW_CARDS.has(id) else Base.card(id)
	if data.get("kind","") == "power":
		return "调整"
	return "快攻" if int(data.get("windup",10)) <= 6 else "重击"

static func joker(id: String) -> Dictionary:
	var data: Dictionary = JOKERS.get(id,{}).duplicate(true)
	if not data.is_empty():
		data["effects"] = JOKER_EFFECTS.get(id,[]).duplicate(true)
	return data

static func evaluate(plan: Array, action_count: int = PLAY) -> Dictionary:
	if action_count < 1 or plan.size() != action_count:
		return {"type":"invalid","name":"选满%d张" % action_count,"flat":0,"mult":1.0,"ranks":[],"tags":[]}
	var ranks: Array[int] = []
	var counts := {}
	for id in plan:
		var key := String(id)
		if not CARD_IDS.has(key):
			return {"type":"invalid","name":"无效动作牌","flat":0,"mult":1.0,"ranks":[],"tags":[]}
		# Pattern search needs ranks only, not a deep copy of every combat effect.
		var rank := int(NEW_CARDS[key].rank) if NEW_CARDS.has(key) else int(Base.CARDS[key].rank)
		ranks.append(rank)
		counts[rank] = int(counts.get(rank,0))+1
	var sorted: Array = counts.keys()
	sorted.sort()
	var type := "scatter"
	var largest := 0
	var pairs := 0
	var run := 0
	var longest_run := 0
	var previous := -100
	for rank in sorted:
		largest = maxi(largest,int(counts[rank]))
		pairs += 1 if int(counts[rank]) >= 2 else 0
		run = run+1 if int(rank) == previous+1 else 1
		longest_run = maxi(longest_run,run)
		previous = int(rank)
	if largest >= 5:
		type = "five"
	elif largest == 4:
		type = "four"
	elif largest == 3 and pairs >= 2:
		type = "full_house"
	elif longest_run >= 5:
		type = "straight"
	elif largest == 3:
		type = "triple"
	elif longest_run >= 3:
		type = "sequence"
	elif pairs >= 2:
		type = "two_pair"
	elif pairs == 1:
		type = "pair"
	var pattern: Dictionary = PATTERNS[type].duplicate(true)
	pattern.merge({"type":type,"ranks":ranks,"ex":false})
	return pattern

static func distance_label(distance: int) -> String:
	return ["贴身","中距","远距"][clampi(distance,0,2)]

static func range_label(card: Dictionary) -> String:
	var first := distance_label(int(card.range_min))
	return first if int(card.range_min)==int(card.range_max) else first+"–"+distance_label(int(card.range_max))

static func outcome_label(kind: String) -> String:
	return {"hit":"命中","counter":"打康","punish":"确反","blocked":"格挡","dodged":"闪避成功","parried":"招架成功","whiff":"打空"}.get(kind,kind)
