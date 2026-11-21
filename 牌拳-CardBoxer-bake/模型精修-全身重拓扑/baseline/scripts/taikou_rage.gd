extends RefCounted
## 怒火槽（Rage / EX gauge）—— 格斗游戏式资源，不是太阁 IV 的「士气」。
##
## 原作士气是第二败北资源（被打光就输）；工程师把它换成怒火槽：
##   * 只有挨打才攒怒（赢的那一回不攒，平局双方各攒）
##   * 攒满后，本回亮出的 3 张牌升 EX：rank 各 +1（封顶 9）再判牌型
##   * 升级反而变弱时保底用原牌（三连·123=700 → 234=602 就是反例）
##   * 触发即清空，只影响这一回；怒火跨局保留，新一场比赛才清零
##
## 纯函数，无节点、无状态：arena.gd 持有双方数值，HUD 只读，实时格斗不碰它。

const Rules = preload("res://scripts/taikou_rules.gd")

const MAX := 100.0
## 每受 1 点伤害攒多少怒火。三回制一局总伤害约 30~50，取 5 让连输两回
## 基本能攒满，不至于整场都用不上 EX。这是平衡参数，改它只需重跑自检。
const PER_DAMAGE := 5.0
const RANK_CAP := 9


static func gain(current: float, damage: int) -> float:
	return clampf(current + float(maxi(damage, 0)) * PER_DAMAGE, 0.0, MAX)


static func is_full(current: float) -> bool:
	return current >= MAX


static func ratio(current: float) -> float:
	return clampf(current / MAX, 0.0, 1.0)


static func upgrade(ranks: Array) -> Array:
	var out: Array = []
	for v: Variant in ranks:
		out.append(mini(int(v) + 1, RANK_CAP))
	return out


static func _same(a: Array, b: Array) -> bool:
	if a.size() != b.size():
		return false
	for i in range(a.size()):
		if int(a[i]) != int(b[i]):
			return false
	return true


## 满槽时调用：返回实际参与判定的 rank 数组、判定结果、是否真的升级了。
## 保底不变量：result.score 恒不低于原牌的 score（1..9 全组合由自检穷举钉死）。
static func best(ranks: Array) -> Dictionary:
	var original: Dictionary = Rules.evaluate(ranks)
	var upgraded: Array = upgrade(ranks)
	var ex: Dictionary = Rules.evaluate(upgraded)
	var use_ex: bool = Rules.compare(ex, original) >= 0 and not _same(upgraded, ranks)
	if use_ex:
		return {"ranks": upgraded, "result": ex, "boosted": true}
	return {"ranks": ranks.duplicate(), "result": original, "boosted": false}
