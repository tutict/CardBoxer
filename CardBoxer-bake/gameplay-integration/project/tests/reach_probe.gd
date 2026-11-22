extends SceneTree
## 判定距离 vs 画出来的拳头：命中的那一刻，画面最远的手/脚伸到哪。
##
##   godot --headless --path . --script res://tests/reach_probe.gd
##
## 为什么要这个探针：`reach` 是「两个人脚下的距离」，画面上能证明它的只有一个数 ——
## 命中信号响起那一 tick 的关节位置。别的算法都是猜：
##   * 拿整条轨道取最大值 → 会把前摇里的伸手算进去（throw 前摇伸到 64，命中帧只有
##     38，用最大值会得出「只短 34」的错误结论，真实是短 60）；
##   * 拿 active 末尾那一帧 → 原来结算在 active 第一 tick，两者差 2~3 帧。
##
## 所以这里退到语义最硬的地方：把两个人摆在**恰好 reach 远**的地方打，听受击方的
## hit_confirmed 信号，在信号那一 tick 读攻方姿势。量到的是「刚好够得着时，画面上
## 拳头在哪」—— 也就是玩家看到的东西。
##
## 弹道牌（bullet）跳过：它的 reach 是飞行距离，不是手臂长度，不可比。

const Defs = preload("res://scripts/card_data.gd")
const FighterScript = preload("res://scripts/fighter.gd")

## 允许「判定比画面长」多少 px。手 6 px 粗、人物 172 px 高，8 px 以内看不出来；
## 反过来（画面比判定长）随便多少都行 —— 那只是挥空，不影响可读性。
const TOL := 8.0

const JOINTS := ["f_hand", "b_hand", "f_foot", "b_foot"]

var _fail := 0
var _rows := 0
var _tick := 0


func _init() -> void:
	print("%-10s %6s %8s %8s %8s  %s" % ["牌", "reach", "画面最远", "差", "命中@tick", "判定"])
	for id: String in Defs.CARDS:
		_probe(id)
	# 假通过闸门：一张牌都没量到却报 PASS，比没有探针更坏。
	if _rows == 0:
		_fail += 1
		print("FAIL 闸门: 一张攻击牌都没量到")
	print("")
	print("量到 %d 张牌，失败 %d 项" % [_rows, _fail])
	print("REACH PROBE: " + ("PASS" if _fail == 0 else "FAIL"))
	quit(0 if _fail == 0 else 1)


func _probe(id: String) -> void:
	var card := Defs.card(id)
	if card.is_empty():
		return
	if String(card.get("kind", "")) != Defs.KIND_ATTACK:
		return
	if bool(card.get("bullet", false)):
		print("%-10s 跳过：弹道牌，reach 是飞行距离" % id)
		return
	var reach := float(card.get("reach", 0))
	if reach <= 0.0:
		return
	_rows += 1

	var attacker: Node2D = FighterScript.new()
	var victim: Node2D = FighterScript.new()
	attacker.is_player = true
	victim.is_player = false
	root.add_child(attacker)
	root.add_child(victim)
	attacker.reset_for_round(400.0, 1)
	# 恰好 reach 远：再远 1 px 就打不到，所以这就是「够得着的极限」。
	victim.reset_for_round(400.0 + reach, -1)
	attacker.opponent = victim
	victim.opponent = attacker
	attacker.meter = 5.0

	# 字典是引用类型，lambda 里的写入能带出来；局部变量会被按值捕获，改了外面看不到。
	var fired := {}
	victim.hit_confirmed.connect(func(_a: bool, _d: int, _b: bool, _dodged: bool) -> void:
		if not fired.has("tick"):
			fired["tick"] = _tick
	)

	if not attacker.play_card(id):
		_fail += 1
		print("FAIL %-9s 出牌失败（气不够/不可行动）" % id)
		return

	var total := int(card.get("windup", 0)) + int(card.get("active", 0)) + int(card.get("recover", 0))
	_tick = 0
	while _tick < total + 6 and not fired.has("tick"):
		_tick += 1
		attacker.tick(Defs.FRAME, 0.0, true)
		victim.tick(Defs.FRAME, 0.0, true)

	if not fired.has("tick"):
		_fail += 1
		print("FAIL %-9s 站在 reach=%.0f 处竟然没打中" % [id, reach])
		attacker.queue_free()
		victim.queue_free()
		return

	# 信号在 victim.tick 里发出，此时攻方这一 tick 已经 tick 过、姿势已更新。
	var pose: Dictionary = attacker._build_pose()
	var far := -1e9
	for key: String in JOINTS:
		far = maxf(far, (pose[key] as Vector2).x)
	var gap := reach - far
	var ok := gap <= TOL
	if not ok:
		_fail += 1
	print("%s %-10s %6.0f %8.1f %8.1f %8d  %s" % [
		"OK " if ok else "FAIL", id, reach, far, gap, int(fired["tick"]),
		"打到" if ok else "隔空命中 %.0f px" % gap])
	attacker.queue_free()
	victim.queue_free()
