extends SceneTree
## 命中结算的三条真语义，用来锁住「打对手而不是打自己」这个修复。
##
##   godot --headless --path . --script res://tests/duel_probe.gd
##
## 1) 命中：攻击方血量不变，受击方掉血并进 HITSTUN
## 2) 格挡：受击方正在 guard，伤害降到两成，且进 BLOCKSTUN
## 3) 打空：距离超出 reach，两边都不掉血
## 4) 受击反应：被打中时膝盖和后脚要动（旧的倾斜代码只动上身七个关节，绝不动腿），
##    硬直结束时必须回到站架
## 前三条都不该让攻击方掉血 —— 这正是修复前的问题。

const Defs = preload("res://scripts/card_data.gd")
const FighterScript = preload("res://scripts/fighter.gd")

const IDLE := 0
const HITSTUN := 2
const BLOCKSTUN := 3

var _fail := 0


func _init() -> void:
	_case_hit()
	_case_block()
	_case_miss()
	_case_react()
	print("")
	print("DUEL PROBE: " + ("PASS" if _fail == 0 else "FAIL"))
	quit(0 if _fail == 0 else 1)


func _duel(dist: float, guard: bool) -> Array:
	var a: Node2D = FighterScript.new()
	var b: Node2D = FighterScript.new()
	a.is_player = true
	b.is_player = false
	root.add_child(a)
	root.add_child(b)
	a.reset_for_round(400.0, 1)
	b.reset_for_round(400.0 + dist, -1)
	a.opponent = b
	b.opponent = a
	a.meter = 5.0
	b.meter = 5.0
	if guard:
		b.play_card("guard")
		for i in range(2):
			b.tick(Defs.FRAME, 0.0, true)
	# 受击方身上发出的 hit_confirmed 是唯一可信的结算记录：blocked 标志和实际
	# 伤害都在里面，不用靠抽帧去猜状态（硬直只有 0.16~0.26 秒，跑完就回 IDLE 了）。
	var seen := {}
	b.hit_confirmed.connect(func(attacker_is_player: bool, damage: int, blocked: bool, dodged: bool) -> void:
		seen["damage"] = damage
		seen["blocked"] = blocked
		seen["attacker_is_player"] = attacker_is_player
	)
	var fired: bool = a.play_card("jab")
	for i in range(24):
		a.tick(Defs.FRAME, 0.0, true)
		b.tick(Defs.FRAME, 0.0, true)
	return [a, b, fired, seen]


func _report(name: String, a: Node2D, b: Node2D, fired: bool, ok: bool, note: String) -> void:
	if not ok:
		_fail += 1
	print("%s %-6s %s  攻 hp=%d 守 hp=%d  (%s)" % [
		"OK " if ok else "FAIL", name, "(出牌成功)" if fired else "(出牌失败!)",
		a.hp, b.hp, note])


func _case_hit() -> void:
	var r := _duel(40.0, false)
	var a: Node2D = r[0]
	var b: Node2D = r[1]
	var seen: Dictionary = r[3]
	var dmg := int(Defs.card("jab")["damage"])
	var ok: bool = bool(r[2]) and a.hp == 100 and b.hp == 100 - dmg \
		and int(seen.get("damage", -1)) == dmg and seen.get("blocked", true) == false \
		and seen.get("attacker_is_player", false) == true
	_report("命中", a, b, bool(r[2]), ok,
		"受击方应掉 %d，信号 blocked=false / attacker_is_player=true" % dmg)


func _case_block() -> void:
	var r := _duel(40.0, true)
	var a: Node2D = r[0]
	var b: Node2D = r[1]
	var seen: Dictionary = r[3]
	var dmg := int(Defs.card("jab")["damage"])
	var reduced := maxi(1, int(round(float(dmg) * 0.2)))
	var ok: bool = bool(r[2]) and a.hp == 100 and b.hp == 100 - reduced \
		and int(seen.get("damage", -1)) == reduced and seen.get("blocked", false) == true
	_report("格挡", a, b, bool(r[2]), ok,
		"应只掉 %d（两成），信号 blocked=true —— 格挡判定必须读到防守方" % reduced)


func _case_miss() -> void:
	var r := _duel(400.0, false)
	var a: Node2D = r[0]
	var b: Node2D = r[1]
	var seen: Dictionary = r[3]
	var ok: bool = bool(r[2]) and a.hp == 100 and b.hp == 100 and seen.is_empty()
	_report("打空", a, b, bool(r[2]), ok, "距离 400 > reach，两边都不该掉血、不该有命中信号")


## 受击反应是否真的被画出来。判据挑在**膝盖**上：老代码的 `_stun_tilt` 只偏移
## 髋/肩/头/四条臂，膝盖和脚永远钉在原地，所以「膝盖动了」这件事唯一可能的来源
## 就是烘好的反应轨道。头用 x 比（呼吸只动 y），膝盖完全没有呼吸项。
func _case_react() -> void:
	var a: Node2D = FighterScript.new()
	var b: Node2D = FighterScript.new()
	a.is_player = true
	b.is_player = false
	root.add_child(a)
	root.add_child(b)
	a.reset_for_round(400.0, 1)
	b.reset_for_round(440.0, -1)
	a.opponent = b
	b.opponent = a
	a.meter = 5.0

	b.tick(Defs.FRAME, 0.0, true)
	var idle: Dictionary = b._build_pose()
	var idle_knee: Vector2 = idle["b_knee"]
	var idle_head: Vector2 = idle["head"]

	if not a.play_card("jab"):
		_fail += 1
		print("FAIL 反应   出牌失败")
		return

	var knee_peak := 0.0
	var head_peak := 0.0
	var stun_ticks := 0
	var back := -1.0
	for _i in range(40):
		a.tick(Defs.FRAME, 0.0, true)
		b.tick(Defs.FRAME, 0.0, true)
		var pose: Dictionary = b._build_pose()
		var knee: Vector2 = pose["b_knee"]
		var head: Vector2 = pose["head"]
		if int(b.state) == HITSTUN:
			stun_ticks += 1
			knee_peak = maxf(knee_peak, knee.distance_to(idle_knee))
			head_peak = maxf(head_peak, absf(head.x - idle_head.x))
		elif stun_ticks > 0 and back < 0.0:
			# 硬直结束后的第一帧：全身都该回到待机姿势，否则恢复控制权时会跳。
			back = maxf(knee.distance_to(idle_knee), absf(head.x - idle_head.x))

	# 判据：膝盖必须明显离开站架（>=6 px，实测 15.7）；头必须后仰（>=12 px，实测 36）；
	# 硬直结束必须回到站架（<=1 px）。三个数字没有一个能靠旧的倾斜代码凑出来。
	var ok := stun_ticks > 0 and knee_peak >= 6.0 and head_peak >= 12.0 \
		and back >= 0.0 and back <= 1.0
	if not ok:
		_fail += 1
	print("%s 反应   硬直 %d 帧  膝盖峰值位移 %.1f px（>=6，仅表能提供）  头部后仰 %.1f px（>=12）  硬直后回位 %.2f px（<=1）" % [
		"OK " if ok else "FAIL", stun_ticks, knee_peak, head_peak, back])
