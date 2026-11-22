extends SceneTree
## 连招与大招的确定性检查。
##
## 自动对战只能证明「打起来了」；连招表是否接得上、气是否扣对，得用固定序列
## 直接调 Fighter.play_card。跑法：
##   godot --headless --path . --script scripts/combo_check.gd

const FighterScript = preload("res://scripts/fighter.gd")

var _failures: Array = []


func _initialize() -> void:
	_check(["jab"], "", 0, "单招不结算连招")
	_check(["jab", "uppercut"], "升龙连", 5, "两连")
	_check(["jab", "cross"], "双刺交叉", 4, "两连交叉")
	_check(["uppercut", "wave"], "空中追击", 6, "上勾接波")
	_check(["rush", "throw"], "贴身摔", 6, "突进接投")
	_check(["jab", "uppercut", "wave"], "终幕·三重奏", 22, "大招")
	_check(["rush", "throw", "uppercut"], "铁壁崩", 20, "大招二")
	_check_stale_history()

	if _failures.is_empty():
		print("COMBO CHECK: 8/8 passed")
		quit(0)
	else:
		for line: String in _failures:
			print("FAIL: ", line)
		print("COMBO CHECK: %d failed" % _failures.size())
		quit(1)


func _check(sequence: Array, want_name: String, want_bonus: int, label: String) -> void:
	var f = FighterScript.new()
	f.is_player = true
	f.meter = 5.0
	for id: String in sequence:
		f.state = 0  # State.IDLE
		f.play_card(id)
	var name := f.combo_name()
	var bonus := f.combo_bonus()
	if name != want_name or bonus != want_bonus:
		_failures.append("%s: 期望 %s/+%d，实际 %s/+%d（序列 %s）" % [
			label, want_name, want_bonus, name, bonus, str(sequence)
		])


## 隔了很久的牌不该被算进连段。_clock 不推进时所有记录都「现在」，所以这里
## 手动把时钟推过窗口，再确认连招没有触发。
func _check_stale_history() -> void:
	var f = FighterScript.new()
	f.is_player = true
	f.meter = 5.0
	f.state = 0
	f.play_card("jab")
	f._clock += 5.0
	f.state = 0
	f.play_card("uppercut")
	if f.combo_name() != "":
		_failures.append("超时清空: 隔了 5 秒仍判成 %s" % f.combo_name())
