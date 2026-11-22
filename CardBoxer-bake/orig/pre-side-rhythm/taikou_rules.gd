extends RefCounted
## 太阁立志传 IV「合战（部队战斗）」的牌型判定 —— 纯函数，无节点、无状态。
##
## 规则来源（多源一致）：游侠《太阁立志传四》攻略指南 / 中文版简单指南、
## 日文 taikou4.shiyo.info 合战页、巴哈姆特全卡片详解。
##   - 绿色数字卡一次出 3 张，双方同时亮牌比大小
##   - 三同张 > 三连张 > 散牌；同张恒大于连张
##   - 三同强弱：111 > 999 > 888 > … > 222（1 最大，然后 9 递减到 2）
##   - 三连强弱：123 > 789 > 678 > … > 234（123 最大，然后起点 7 递减到 2）
##   - 红色特殊卡压过一切（P2 再接；这里预留 TYPE_SPECIAL 的分段）
##
## score 分段是「同张恒大于连张」的机器判据，别改成连续数值：
##   三同 702..800 | 三连 602..700 | 散牌 101..127
## 也就是最低的三同（222=702）仍然高于最高的三连（123=700）。

const TYPE_TRIPLE := "triple"
const TYPE_SEQUENCE := "sequence"
const TYPE_SCATTER := "scatter"
const TYPE_SPECIAL := "special"

## 3 张 rank（1..9）→ {"type", "score", "name", "sum"}。
static func evaluate(ranks: Array) -> Dictionary:
	var vals: Array[int] = []
	for v: Variant in ranks:
		vals.append(int(v))
	if vals.size() != 3:
		return {"type": "", "score": -1, "name": "无效牌组", "sum": 0}
	var s: Array[int] = vals.duplicate()
	s.sort()
	var a: int = s[0]
	var b: int = s[1]
	var c: int = s[2]
	var total: int = a + b + c
	if a == b and b == c:
		return {
			"type": TYPE_TRIPLE,
			"score": 700 + (100 if a == 1 else a),
			"name": "三同·%d%d%d" % [a, a, a],
			"sum": total,
		}
	if b == a + 1 and c == b + 1:
		return {
			"type": TYPE_SEQUENCE,
			"score": 600 + (100 if a == 1 else a),
			"name": "三连·%d%d%d" % [a, b, c],
			"sum": total,
		}
	return {
		"type": TYPE_SCATTER,
		"score": 100 + total,
		"name": "散牌·和%d" % total,
		"sum": total,
	}


## 1 = 左边赢，-1 = 右边赢，0 = 平局（双方同分）。
static func compare(a: Dictionary, b: Dictionary) -> int:
	var sa: int = int(a.get("score", -1))
	var sb: int = int(b.get("score", -1))
	if sa > sb:
		return 1
	if sa < sb:
		return -1
	return 0


## 赢家造成的伤害。牌型决定底数，点数和补一点零头。
static func damage_of(result: Dictionary) -> int:
	var base := 5
	match String(result.get("type", "")):
		TYPE_TRIPLE:
			base = 14
		TYPE_SEQUENCE:
			base = 10
	return base + int(result.get("sum", 0)) / 3


## 从手牌（通常是 5 张）里穷举所有 3 张组合，返回 score 最高的那组下标。
## 只有 C(5,3)=10 组，穷举比启发式可靠，也方便自检逐条核对。
static func best_combination(ranks: Array) -> Array:
	var best: Array = []
	var best_score := -1
	for i in range(ranks.size() - 2):
		for j in range(i + 1, ranks.size() - 1):
			for k in range(j + 1, ranks.size()):
				var res: Dictionary = evaluate([ranks[i], ranks[j], ranks[k]])
				var sc: int = int(res["score"])
				if sc > best_score:
					best_score = sc
					best = [i, j, k]
	return best


## 牌型显示色：三同最亮、三连次之、散牌最暗。UI 用。
static func type_label(type: String) -> String:
	match type:
		TYPE_TRIPLE:
			return "三同张"
		TYPE_SEQUENCE:
			return "三连张"
		TYPE_SCATTER:
			return "散牌"
		TYPE_SPECIAL:
			return "秘策"
	return ""
