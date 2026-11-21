extends SceneTree
## 怒火槽纯函数自检：攒怒、封顶、EX 升级、保底不变弱。
##
## 跑法：godot --headless --path . --script res://tests/taikou_rage_check.gd
## 退出码 0 = 全过，1 = 有断言失败。
##
## 最重要的一条是 _check_invariant()：穷举 rank 1..9 的全部有序三元组，
## 钉死「EX 判定结果恒不低于原牌」——否则 123 这种最强牌会因为升 EX 反而变弱。

const Rage = preload("res://scripts/taikou_rage.gd")
const Rules = preload("res://scripts/taikou_rules.gd")

var _failures: Array = []
var _total := 0


func _expect(ok: bool, label: String) -> void:
	_total += 1
	if not ok:
		_failures.append(label)


func _initialize() -> void:
	_check_gain()
	_check_upgrade()
	_check_best()
	_check_invariant()
	if _failures.is_empty():
		print("TAIKOU RAGE CHECK: %d/%d passed" % [_total, _total])
		quit(0)
	else:
		for line: String in _failures:
			print("FAIL: ", line)
		print("TAIKOU RAGE CHECK: %d/%d failed" % [_failures.size(), _total])
		quit(1)


func _check_gain() -> void:
	_expect(Rage.gain(0.0, 0) == 0.0, "不受伤不攒怒")
	_expect(Rage.gain(0.0, 4) == 20.0, "每点伤害攒 PER_DAMAGE，实际 %f" % Rage.gain(0.0, 4))
	_expect(Rage.gain(95.0, 10) == Rage.MAX, "怒火应封顶 100")
	_expect(Rage.gain(0.0, -3) == 0.0, "负伤害不该倒扣怒火")
	_expect(not Rage.is_full(99.9), "未满不算满槽")
	_expect(Rage.is_full(100.0), "100 算满槽")
	_expect(Rage.ratio(0.0) == 0.0, "ratio 0 -> 0")
	_expect(Rage.ratio(50.0) == 0.5, "ratio 50 -> 0.5")
	_expect(Rage.ratio(200.0) == 1.0, "ratio 上限 1")


func _check_upgrade() -> void:
	_expect(Rage.upgrade([1, 2, 3]) == [2, 3, 4], "rank 各 +1")
	_expect(Rage.upgrade([9, 9, 9]) == [9, 9, 9], "rank 封顶 9")
	_expect(Rage.upgrade([8, 9, 1]) == [9, 9, 2], "混合封顶")
	_expect(Rage.upgrade([1, 1, 1]) == [2, 2, 2], "111 升级成 222")


func _check_best() -> void:
	var a: Dictionary = Rage.best([1, 2, 3])
	_expect(not bool(a["boosted"]), "123 升级成 234 反而变弱，应保底")
	_expect(a["ranks"] == [1, 2, 3], "保底时应显示原牌")
	_expect(int(a["result"]["score"]) == 700, "保底后仍是三连·123 的 700 分")

	var b: Dictionary = Rage.best([2, 2, 2])
	_expect(bool(b["boosted"]), "222 -> 333 变强，应升级")
	_expect(b["ranks"] == [3, 3, 3], "升级后 rank 为 333")
	_expect(int(b["result"]["score"]) == 703, "333 分数应为 703")

	var c: Dictionary = Rage.best([9, 9, 9])
	_expect(not bool(c["boosted"]), "全 9 升级无变化，不应算 boosted")
	_expect(c["ranks"] == [9, 9, 9], "全 9 保底仍显示原牌")

	var d: Dictionary = Rage.best([4, 6, 9])
	_expect(bool(d["boosted"]), "散牌升级后点数和更大，应升级")
	_expect(d["ranks"] == [5, 7, 9], "散牌升级后 rank")

	var e: Dictionary = Rage.best([7, 8, 9])
	_expect(not bool(e["boosted"]), "789 升级后掉成散牌，应保底")


func _check_invariant() -> void:
	# 729 组有序三元组：EX 结果分数恒不低于原牌，且返回的 result 与 ranks 自洽。
	for x in range(1, 10):
		for y in range(1, 10):
			for z in range(1, 10):
				var ranks: Array = [x, y, z]
				var original: Dictionary = Rules.evaluate(ranks)
				var got: Dictionary = Rage.best(ranks)
				_expect(
					Rules.compare(got["result"], original) >= 0,
					"保底不变量被破坏 %s" % str(ranks)
				)
				_expect(
					Rules.compare(got["result"], Rules.evaluate(got["ranks"])) == 0,
					"返回的 result 必须与实际显示的 ranks 一致 %s" % str(ranks)
				)
