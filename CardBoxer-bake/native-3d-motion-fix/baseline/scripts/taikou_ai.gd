extends RefCounted
## 太阁 IV 合战模式的对手决策（纯函数，无状态）。
##
## 不做难度分级：P0 先把「对手会凑牌型」这件事做对，让玩家有压力。
## 穷举只有 C(5,3)=10 组，用 taikou_rules.best_combination 取最高分，
## 比一堆启发式可靠，也和自检共用同一套判据。

const Rules = preload("res://scripts/taikou_rules.gd")
const Defs = preload("res://scripts/card_data.gd")


static func ranks_of(hand: Array) -> Array:
	var out: Array = []
	for id: Variant in hand:
		var card: Dictionary = Defs.card(String(id))
		out.append(int(card.get("rank", 1)))
	return out


## 出牌：返回 3 个手牌下标，使牌型分最高。
static func choose_play(hand: Array) -> Array:
	return Rules.best_combination(ranks_of(hand))


## 弃牌：保留最优 3 张，把其余 2 张换掉，下一轮重新凑。
## 太阁 IV 每轮最多弃 3 张；这里弃 2 张是「留 3 张成型组」的自然结果。
static func choose_discards(hand: Array) -> Array:
	var keep: Array = Rules.best_combination(ranks_of(hand))
	var out: Array = []
	for i in range(hand.size()):
		if not keep.has(i):
			out.append(i)
	return out
