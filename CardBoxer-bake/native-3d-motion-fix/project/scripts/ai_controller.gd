class_name AIController
extends RefCounted
## 对手的读牌 AI。
##
## 它不是随机的：每一拍都先看距离，再看玩家处在哪个阶段（前摇/硬直/空闲），
## 最后才在手里的牌里挑一张。玩家的四类牌都有对应的应对，所以「读」是有
## 回报的——这也正是流水线 spec 里那条 failure_pressure：
## "Attacking outside the window deals reduced damage and leaves the player exposed."

const Defs = preload("res://scripts/card_data.gd")

const RANGE_CLOSE := 128.0
const RANGE_MID := 300.0

var fighter: Fighter
var reaction := 0.34
var aggression := 0.62

var _timer := 0.0
var _hold_move := 0.0
var _last_played := ""


func _init(owner_fighter: Fighter, level: int = 1) -> void:
	fighter = owner_fighter
	match level:
		1:
			reaction = 0.42
			aggression = 0.5
		2:
			reaction = 0.30
			aggression = 0.62
		_:
			reaction = 0.19
			aggression = 0.74


## 返回 {"play": 手牌下标或 -1, "move": -1/0/1}。
func update(delta: float, player: Fighter, hand: Array) -> Dictionary:
	_timer -= delta
	_hold_move = move_toward(_hold_move, 0.0, delta * 4.0)
	if _timer > 0.0:
		return {"play": -1, "move": _hold_move}

	_timer = reaction * randf_range(0.8, 1.25)
	var dx := player.position.x - fighter.position.x
	var dist := absf(dx)
	var toward := 1.0 if dx > 0.0 else -1.0

	# 1. 玩家前摇中：优先防、闪，或者用投技抢先手。
	if player.is_winding_up() and dist < RANGE_MID:
		var defend := _find(hand, ["sidestep", "guard"])
		if defend >= 0 and randf() < 0.72:
			return {"play": defend, "move": 0.0}
		var grab := _find(hand, ["throw"])
		if grab >= 0 and dist < 130.0 and randf() < 0.5:
			return {"play": grab, "move": 0.0}

	# 2. 玩家后摇中：这是唯一稳赚的窗口，贴上去打。
	if player.is_recovering() and dist < 220.0:
		var punish := _find(hand, ["uppercut", "sweep", "cross", "jab"])
		if punish >= 0:
			return {"play": punish, "move": 0.0}
		var dash := _find(hand, ["rush"])
		if dash >= 0 and dist > RANGE_CLOSE:
			return {"play": dash, "move": 0.0}

	# 3. 连招接续：够得着才接。连招本身不造成位移，接在打不到的距离上
	#    只是把气花掉再吃一个后摇。
	var chain := _chain_card(hand)
	if chain >= 0 and _reach_ok(hand[chain], dist):
		return {"play": chain, "move": 0.0}

	# 3.5 手里凑齐了一套大招且气够：从现在开始打第一张，把整套走完。
	var super_start := _super_plan(hand, dist)
	if super_start >= 0:
		return {"play": super_start, "move": 0.0}

	# 4. 远距离：发波、突进、或者干脆走上去。
	if dist > 210.0:
		var wave := _find(hand, ["wave"])
		if wave >= 0 and randf() < 0.6:
			return {"play": wave, "move": 0.0}
		var rush_far := _find(hand, ["rush"])
		if rush_far >= 0 and randf() < 0.5:
			return {"play": rush_far, "move": 0.0}
		_hold_move = toward
		return {"play": -1, "move": toward}

	# 5. 中距离（104-210）：只有扫腿这类长手牌够得着，其余先贴近。
	if dist > 104.0:
		var long_reach := _find_reaching(hand, dist, ["sweep", "cross", "jab"])
		if long_reach >= 0 and randf() < 0.72:
			return {"play": long_reach, "move": 0.0}
		var rush_mid := _find(hand, ["rush"])
		if rush_mid >= 0 and randf() < 0.35:
			return {"play": rush_mid, "move": 0.0}
		_hold_move = toward
		return {"play": -1, "move": toward}

	# 6. 贴身：投技破防、上勾拳起手，偶尔蓄势。
	if fighter.meter < 1.0 and randf() < 0.22:
		var focus := _find(hand, ["focus"])
		if focus >= 0:
			return {"play": focus, "move": 0.0}
	var grab := _find(hand, ["throw"])
	if grab >= 0 and randf() < 0.34:
		return {"play": grab, "move": 0.0}
	var attack := _find(hand, ["uppercut", "sweep", "cross", "jab"])
	if attack >= 0 and randf() < aggression + 0.2:
		return {"play": attack, "move": 0.0}
	var guard := _find(hand, ["guard"])
	if guard >= 0 and randf() < 0.18:
		return {"play": guard, "move": 0.0}

	# 7. 兜底：手里确实没有能打人的牌时，别站着不动。
	#    先出 0 费的守御/蓄力（保命、攒气），再考虑用位移牌离开原地。
	for group: Array in [["sidestep"], ["guard"], ["focus"], ["recover"], ["backstep"], ["rush"]]:
		var idx := _find(hand, group)
		if idx >= 0:
			return {"play": idx, "move": 0.0}
	return {"play": -1, "move": 0.0}


## 如果整手牌凑得出一套大招、气也够，就返回起手那张的下标。
## AI 是单步决策的，没有这一步它永远凑不齐三张连续牌。
func _super_plan(hand: Array, dist: float) -> int:
	for entry: Dictionary in Defs.SUPERS:
		if int(entry["cost"]) > int(fighter.meter):
			continue
		var seq: Array = entry["seq"]
		var first := -1
		var ok := true
		for card_id: String in seq:
			var idx := _find(hand, [card_id])
			if idx < 0:
				ok = false
				break
			if first < 0:
				first = idx
		if ok and first >= 0 and _reach_ok(hand[first], dist):
			return first
	return -1


## 这张牌打这个距离能不能命中。位移与守御牌没有射程概念，一律算可用。
func _reach_ok(id: Variant, dist: float) -> bool:
	if id == null:
		return false
	var card := Defs.card(String(id))
	if card.is_empty():
		return false
	if String(card.get("kind", "")) != Defs.KIND_ATTACK:
		return true
	if bool(card.get("bullet", false)):
		return true
	return float(card.get("reach", 0)) >= dist


## 按名字优先级找一个「射程够得到 dist」的牌。
func _find_reaching(hand: Array, dist: float, names: Array) -> int:
	for raw_name: String in names:
		var idx := _find(hand, [raw_name])
		if idx < 0:
			continue
		var card := Defs.card(String(hand[idx]))
		if float(card.get("reach", 0)) >= dist:
			return idx
	return -1


## 找到能接在上一张牌后面的牌。只在气够的时候接大招。
func _chain_card(hand: Array) -> int:
	if _last_played == "":
		return -1
	for entry: Dictionary in Defs.SUPERS:
		var seq: Array = entry["seq"]
		if seq.size() > 1 and String(seq[seq.size() - 2]) == _last_played:
			var nxt := String(seq[seq.size() - 1])
			if int(entry["cost"]) <= int(fighter.meter):
				var idx := _find(hand, [nxt])
				if idx >= 0:
					return idx
	for entry: Dictionary in Defs.COMBOS:
		var seq: Array = entry["seq"]
		if seq.size() > 1 and String(seq[seq.size() - 2]) == _last_played:
			var idx := _find(hand, [String(seq[seq.size() - 1])])
			if idx >= 0:
				return idx
	return -1


func note_played(card_id: String) -> void:
	_last_played = card_id


## 手牌里找第一张名字在 wanted 里的牌。空格（null）与气不够的牌跳过——
## 不跳过的话 AI 会一直去点打不出来的牌，玩家看到的就是它站桩不动。
func _find(hand: Array, wanted: Array) -> int:
	for i in range(hand.size()):
		var id: Variant = hand[i]
		if id == null:
			continue
		var card := Defs.card(String(id))
		if card.is_empty():
			continue
		if int(card.get("cost", 0)) > int(fighter.meter):
			continue
		for name_wanted: String in wanted:
			if String(id) == name_wanted:
				return i
	return -1
