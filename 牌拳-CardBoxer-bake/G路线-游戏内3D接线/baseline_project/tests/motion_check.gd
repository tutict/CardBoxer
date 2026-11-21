extends SceneTree
## 招式表自检：证明「表 → 游戏」这条接线没有错位。
##
## 跑法（游戏目录下）：
##   godot --headless --path . --script res://tests/motion_check.gd
## 退出码 0 = 全过，1 = 有断言失败。
##
## 三条断言，各自防一件具体的事：
##   1) 12 张牌都有轨迹，帧数 = split 之和     → 防漏烘 / JSON 截断
##   2) split == card_data 的 windup/active/recover → 防「表与游戏帧数漂移」，
##      这条一旦坏了，姿势就会和伤害结算脱钩，画面上完全看不出来
##   3) sample() 逐帧回读 == 表里的原值，且 facing=-1 精确镜像
##      → 防取帧下标算错、防镜像漏翻（漏翻会变成背身出拳）

const Defs = preload("res://scripts/card_data.gd")
const Motion = preload("res://scripts/card_motion.gd")
const PATH := "res://data/card_motion.json"

var _fail := 0
var _checked_frames := 0
var _checked_values := 0


func _init() -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(PATH))
	if typeof(parsed) != TYPE_DICTIONARY:
		_fail += 1
		print("FAIL: 表读不出来或不是字典")
		quit(1)
		return
	var cards: Dictionary = (parsed as Dictionary).get("cards", {})

	_check_coverage(cards)
	_check_split(cards)
	_check_readback(cards)

	print("")
	print("检查帧数 %d，比对数值 %d 个，失败 %d 项" % [_checked_frames, _checked_values, _fail])
	print("MOTION CHECK: " + ("PASS" if _fail == 0 else "FAIL"))
	quit(0 if _fail == 0 else 1)


# 1) 覆盖：Defs.CARDS 里每张牌都要有轨迹。
func _check_coverage(cards: Dictionary) -> void:
	var missing: Array = []
	for id: String in Defs.CARDS:
		if not cards.has(id):
			missing.append(id)
			continue
		var entry: Dictionary = cards[id]
		var track: Array = entry.get("track", [])
		var split: Array = entry.get("split", [])
		var total := 0
		for n in split:
			total += int(n)
		if track.is_empty():
			missing.append("%s(空轨迹)" % id)
		elif int(entry.get("frames", -1)) != total:
			missing.append("%s(frames=%s != split和=%d)" % [id, entry.get("frames"), total])
	if missing.is_empty():
		print("OK 覆盖: %d 张牌全部有轨迹且帧数自洽" % Defs.CARDS.size())
	else:
		_fail += 1
		print("FAIL 覆盖: " + ", ".join(missing))


# 2) 相位帧数必须与游戏结算用的帧数一致。
func _check_split(cards: Dictionary) -> void:
	var bad: Array = []
	for id: String in Defs.CARDS:
		if not cards.has(id):
			bad.append(id + "(无表)")
			continue
		var card: Dictionary = Defs.card(id)
		var want := [
			int(card.get("windup", 4)),
			int(card.get("active", 3)),
			int(card.get("recover", 8)),
		]
		var got: Array = cards[id].get("split", [])
		if got.size() != 3 or int(got[0]) != want[0] or int(got[1]) != want[1] or int(got[2]) != want[2]:
			bad.append("%s 表%s vs 游戏%s" % [id, str(got), str(want)])
	if bad.is_empty():
		print("OK 相位: 12 张牌的 split 与 windup/active/recover 完全一致")
	else:
		_fail += 1
		print("FAIL 相位: " + " | ".join(bad))


# 3) 逐帧回读：对每一帧构造一个必然落在该帧的进度，比对整副关节。
func _check_readback(cards: Dictionary) -> void:
	var worst := 0.0
	var bad: Array = []
	for id: String in cards:
		var entry: Dictionary = cards[id]
		var track: Array = entry.get("track", [])
		var split: Array = entry.get("split", [])
		var phases := ["windup", "active", "recover"]
		for p in range(3):
			var count := int(split[p])
			for i in range(count):
				var global := 0
				for q in range(p):
					global += int(split[q])
				global += i
				# (i + 0.5) / count 一定落在第 i 帧（int() 取整不会进位）
				var progress := (float(i) + 0.5) / float(count)
				var got := Motion.sample(id, phases[p], progress, 1.0)
				_checked_frames += 1
				if got.is_empty():
					bad.append("%s f%d 取不到" % [id, global + 1])
					continue
				var raw: Dictionary = track[global]
				for key: String in Motion.JOINTS:
					var want: Array = raw[key]
					var have: Vector2 = got[key]
					worst = maxf(worst, absf(have.x - float(want[0])))
					worst = maxf(worst, absf(have.y - float(want[1])))
					_checked_values += 2
					if absf(have.x - float(want[0])) > 1e-4 or absf(have.y - float(want[1])) > 1e-4:
						bad.append("%s f%d %s 得到%s 期望%s" % [id, global + 1, key, str(have), str(Vector2(want[0], want[1]))])
				# 镜像：-1 时 x 与 lean 精确取反，y 不动
				var mir := Motion.sample(id, phases[p], progress, -1.0)
				for key: String in Motion.JOINTS:
					var a: Vector2 = got[key]
					var b: Vector2 = mir[key]
					if absf(b.x + a.x) > 1e-4 or absf(b.y - a.y) > 1e-4:
						bad.append("%s f%d %s 镜像错" % [id, global + 1, key])
				if absf(float(mir["lean"]) + float(got["lean"])) > 1e-4:
					bad.append("%s f%d lean 镜像错" % [id, global + 1])
	if bad.is_empty():
		print("OK 回读: 逐帧逐关节一致，最大误差 %.6f px，镜像精确" % worst)
	else:
		_fail += 1
		print("FAIL 回读(%d 处): %s" % [bad.size(), " | ".join(bad.slice(0, 8))])
