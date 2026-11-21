extends SceneTree
## 太阁 IV 合战牌型的确定性自检。
##
## 跑法：godot --headless --path . --script res://tests/taikou_rules_check.gd
## 退出码 0 = 全过，1 = 有断言失败。
##
## 这些排序反直觉（1 最大、123 最大、同张恒压连张），靠人眼复查一定会漏，
## 所以逐条列出而不是只测几个代表值。

const Rules = preload("res://scripts/taikou_rules.gd")
const Defs = preload("res://scripts/card_data.gd")

var _failures: Array = []
var _total := 0


func _init() -> void:
	_check_types()
	_check_triple_order()
	_check_sequence_order()
	_check_triple_beats_sequence()
	_check_scatter_order()
	_check_compare_draw()
	_check_damage()
	_check_best_combination()
	_check_rank_mapping()
	_check_invalid()

	if _failures.is_empty():
		print("TAIKOU RULES CHECK: %d/%d passed" % [_total, _total])
		quit(0)
	else:
		for line: String in _failures:
			print("FAIL: ", line)
		print("TAIKOU RULES CHECK: %d/%d failed" % [_failures.size(), _total])
		quit(1)


func _expect(ok: bool, label: String) -> void:
	_total += 1
	if not ok:
		_failures.append(label)


func _score(ranks: Array) -> int:
	return int(Rules.evaluate(ranks)["score"])


func _check_types() -> void:
	_expect(String(Rules.evaluate([1, 1, 1])["type"]) == Rules.TYPE_TRIPLE, "111 应判三同")
	_expect(String(Rules.evaluate([7, 9, 8])["type"]) == Rules.TYPE_SEQUENCE, "无序 7/9/8 应判三连 789")
	_expect(String(Rules.evaluate([1, 5, 9])["type"]) == Rules.TYPE_SCATTER, "159 应判散牌")
	_expect(String(Rules.evaluate([1, 1, 2])["type"]) == Rules.TYPE_SCATTER, "对子不是牌型，应判散牌")
	_expect(String(Rules.evaluate([1, 3, 2])["type"]) == Rules.TYPE_SEQUENCE, "132 重排后应判三连 123")


func _check_triple_order() -> void:
	var order := [[1, 1, 1], [9, 9, 9], [8, 8, 8], [7, 7, 7], [6, 6, 6],
		[5, 5, 5], [4, 4, 4], [3, 3, 3], [2, 2, 2]]
	for i in range(order.size() - 1):
		_expect(
			_score(order[i]) > _score(order[i + 1]),
			"三同排序 %s 应大于 %s" % [str(order[i]), str(order[i + 1])]
		)


func _check_sequence_order() -> void:
	var order := [[1, 2, 3], [7, 8, 9], [6, 7, 8], [5, 6, 7],
		[4, 5, 6], [3, 4, 5], [2, 3, 4]]
	for i in range(order.size() - 1):
		_expect(
			_score(order[i]) > _score(order[i + 1]),
			"三连排序 %s 应大于 %s" % [str(order[i]), str(order[i + 1])]
		)


func _check_triple_beats_sequence() -> void:
	# 最弱三同必须仍然压过最强三连，这是「同张大于连张」的边界。
	_expect(_score([2, 2, 2]) > _score([1, 2, 3]), "222 应大于 123")
	for r in range(2, 10):
		_expect(
			_score([r, r, r]) > _score([1, 2, 3]),
			"三同 %d 应大于最强三连 123" % r
		)


func _check_scatter_order() -> void:
	# 每组都必须是真散牌（不能凑成三连），且点数和严格递减。
	# 别写成 [9,9,7] > [9,8,8]：两组和都是 25，规则上就该是平局。
	var order := [[9, 9, 8], [9, 9, 7], [9, 9, 6], [1, 2, 4], [1, 2, 3]]
	# 最后一组是三连，不计入散牌序列；单独确认它比任何散牌都大。
	for i in range(order.size() - 2):
		_expect(
			_score(order[i]) > _score(order[i + 1]),
			"散牌按和排序 %s 应大于 %s" % [str(order[i]), str(order[i + 1])]
		)
	_expect(_score([9, 9, 7]) == _score([9, 8, 8]), "点数和相同的两组散牌应判平局")
	_expect(_score([2, 3, 4]) > _score([9, 9, 8]), "最弱三连仍应大于最强散牌")


func _check_compare_draw() -> void:
	var a: Dictionary = Rules.evaluate([1, 1, 1])
	var b: Dictionary = Rules.evaluate([1, 1, 1])
	_expect(Rules.compare(a, b) == 0, "同牌型同分应判平局")
	_expect(Rules.compare(Rules.evaluate([1, 1, 1]), Rules.evaluate([2, 3, 4])) == 1, "111 应赢 234")
	_expect(Rules.compare(Rules.evaluate([2, 3, 4]), Rules.evaluate([1, 1, 1])) == -1, "234 应输 111")


func _check_damage() -> void:
	# 同 sum 时牌型底数必须拉开，否则凑牌型就没有回报。
	var t: Dictionary = {"type": Rules.TYPE_TRIPLE, "sum": 12}
	var s: Dictionary = {"type": Rules.TYPE_SEQUENCE, "sum": 12}
	var c: Dictionary = {"type": Rules.TYPE_SCATTER, "sum": 12}
	_expect(Rules.damage_of(t) > Rules.damage_of(s), "三同伤害应大于三连")
	_expect(Rules.damage_of(s) > Rules.damage_of(c), "三连伤害应大于散牌")


func _check_best_combination() -> void:
	var a: Array = Rules.best_combination([1, 1, 1, 8, 9])
	_expect(a == [0, 1, 2], "有 111 时应选前三张，实际 %s" % str(a))
	var b: Array = Rules.best_combination([2, 3, 4, 8, 9])
	_expect(b == [0, 1, 2], "234 应优于任何散牌，实际 %s" % str(b))
	var c: Array = Rules.best_combination([8, 9, 1, 2, 3])
	# 123 在下标 2/3/4，且 123 是最大三连。
	_expect(c == [2, 3, 4], "乱序时应找出 123，实际 %s" % str(c))


func _check_rank_mapping() -> void:
	for id: String in Defs.CARDS:
		var card: Dictionary = Defs.CARDS[id]
		_expect(card.has("rank"), "%s 缺 rank 字段" % id)
		if card.has("rank"):
			var r: int = int(card["rank"])
			_expect(r >= 1 and r <= 9, "%s 的 rank=%d 越界" % [id, r])
	for id: String in Defs.DECK:
		_expect(Defs.CARDS.has(id), "DECK 里的 %s 不在 CARDS 中" % id)


func _check_invalid() -> void:
	_expect(int(Rules.evaluate([1, 2])["score"]) == -1, "不足 3 张应判无效")
	_expect(int(Rules.evaluate([1, 2, 3, 4])["score"]) == -1, "超过 3 张应判无效")
