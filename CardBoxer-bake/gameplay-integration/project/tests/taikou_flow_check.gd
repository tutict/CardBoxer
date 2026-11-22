extends SceneTree
## 回合制合战的输入 / 状态机自检。
##
## 跑法：godot --headless --path . --script res://tests/taikou_flow_check.gd
## 退出码 0 = 全过，1 = 有断言失败。
##
## 为什么需要它：引擎内截帧用的是 CARD_BOXER_TAIKOU_BOT（AI 直接决策），
## 真人路径「1-5 勾选 → 空格确认」一次都没被执行过。这里直接实例化 arena
## 并逐阶段调用输入函数，把弃牌、选牌上限、亮牌、结算、补牌走一遍。
##
## 特别钉住一条：亮牌阶段不允许掉血。perform_visual() 只播动画，
## 伤害必须等 _resolve_taikou() 统一结算，否则会双重结算。

const ArenaScript = preload("res://scripts/arena.gd")
const Rules = preload("res://scripts/taikou_rules.gd")
const Rage = preload("res://scripts/taikou_rage.gd")

var _failures: Array = []
var _total := 0
var a


func _initialize() -> void:
	OS.set_environment("CARD_BOXER_BATTLE_MODE", "taikou")
	a = ArenaScript.new()
	root.add_child(a)
	# SceneTree._initialize() 阶段主循环还没起，add_child 不会触发 _ready()，
	# player / enemy / hand 会全是 Nil，断言就成了假红。显式跑一次。
	if a.player == null:
		a._ready()
	a.round_phase = "fight"

	_check_discard()
	_check_select()
	_check_reveal()
	_check_resolve()
	_check_finish()
	_check_draw()
	_check_turn_limit()
	_check_rage()
	_check_mode_switch()

	if _failures.is_empty():
		print("TAIKOU FLOW CHECK: %d/%d passed" % [_total, _total])
		quit(0)
	else:
		for line: String in _failures:
			print("FAIL: ", line)
		print("TAIKOU FLOW CHECK: %d/%d failed" % [_failures.size(), _total])
		quit(1)


func _expect(ok: bool, label: String) -> void:
	_total += 1
	if not ok:
		_failures.append(label)


func _hand_full(hand: Array) -> bool:
	if hand.size() != 5:
		return false
	for id: Variant in hand:
		if id == null:
			return false
	return true


func _check_discard() -> void:
	_expect(a.tk_phase == "discard", "开局应在弃牌阶段")
	_expect(_hand_full(a.hand), "起手 5 张不能有空槽")
	a._taikou_toggle(0)
	a._taikou_toggle(1)
	_expect(a.tk_marks == [0, 1], "勾选两张应记为 [0,1]，实际 %s" % str(a.tk_marks))
	a._taikou_toggle(0)
	_expect(a.tk_marks == [1], "再按同一张应取消勾选，实际 %s" % str(a.tk_marks))
	a._taikou_confirm()
	_expect(a.tk_phase == "select", "确认弃牌后应进入选牌阶段")
	_expect(a.tk_marks.is_empty(), "切阶段要清空勾选")
	_expect(_hand_full(a.hand), "弃牌换牌后手牌仍应是 5 张非 null")
	_expect(_hand_full(a.enemy_hand), "对手弃牌换牌后也应是 5 张非 null")


func _check_select() -> void:
	a._taikou_toggle(0)
	a._taikou_toggle(1)
	a._taikou_toggle(2)
	_expect(a.tk_marks.size() == 3, "应能选满 3 张")
	a._taikou_toggle(3)
	_expect(a.tk_marks.size() == 3, "选牌上限 3 张，第 4 张不该加进来")
	a._taikou_confirm()
	_expect(a.tk_phase == "reveal", "确认亮牌后应进入 reveal")
	_expect(a.tk_player_reveal.size() == 3, "玩家应亮出 3 个点数")
	_expect(a.tk_enemy_reveal.size() == 3, "对手应亮出 3 个点数")
	_expect(String(a.tk_player_result.get("type", "")) != "", "玩家牌型必须被判定")
	_expect(String(a.tk_enemy_result.get("type", "")) != "", "对手牌型必须被判定")


func _check_reveal() -> void:
	var empties := 0
	for id: Variant in a.hand:
		if id == null:
			empties += 1
	_expect(empties == 3, "亮出的 3 张应从手牌移除，实际空槽 %d 个" % empties)
	# 承重断言：亮牌阶段绝不能掉血，否则 perform_visual 漏了实时结算守卫。
	_expect(a.player.hp == 100, "亮牌阶段玩家不该掉血，实际 %d" % a.player.hp)
	_expect(a.enemy.hp == 100, "亮牌阶段对手不该掉血，实际 %d" % a.enemy.hp)
	_expect(a.player._visual_only, "玩家应处于纯表演状态")
	_expect(a.enemy._visual_only, "对手应处于纯表演状态")


func _check_resolve() -> void:
	var p_before: int = a.player.hp
	var e_before: int = a.enemy.hp
	a._resolve_taikou()
	_expect(a.tk_phase == "resolve", "结算后应进入 resolve")
	var cmp: int = Rules.compare(a.tk_player_result, a.tk_enemy_result)
	if cmp > 0:
		_expect(a.tk_winner == "player", "玩家牌型更大时应判玩家赢")
		_expect(a.enemy.hp < e_before, "玩家赢时对手该掉血")
		_expect(a.player.hp == p_before, "玩家赢时自己不该掉血")
	elif cmp < 0:
		_expect(a.tk_winner == "enemy", "对手牌型更大时应判对手赢")
		_expect(a.player.hp < p_before, "对手赢时玩家该掉血")
		_expect(a.enemy.hp == e_before, "对手赢时自己不该掉血")
	else:
		_expect(a.tk_winner == "draw", "同分应判平局")
		_expect(a.player.hp < p_before and a.enemy.hp < e_before, "平局双方各受 3 点")
	_expect(a.tk_damage > 0, "结算伤害应为正数")


func _check_finish() -> void:
	a._finish_taikou_turn()
	_expect(_hand_full(a.hand), "回合结束玩家手牌应补满 5 张")
	_expect(_hand_full(a.enemy_hand), "回合结束对手手牌应补满 5 张")
	_expect(a.tk_turn == 2, "轮数应推进到第 2 轮，实际 %d" % a.tk_turn)
	_expect(a.tk_phase == "discard", "新一轮应回到弃牌阶段")


## 实战日志里没出现过平局，这里手动构造同分，确认结算层走的是「各受 3 点」。
func _check_draw() -> void:
	a.player.reset_for_round(430, 1)
	a.enemy.reset_for_round(850, -1)
	a.tk_player_result = Rules.evaluate([1, 1, 1])
	a.tk_enemy_result = Rules.evaluate([1, 1, 1])
	a._resolve_taikou()
	_expect(a.tk_winner == "draw", "同分应判平局")
	_expect(a.player.hp == 97 and a.enemy.hp == 97, "平局双方各受 3 点，实际 %d/%d" % [a.player.hp, a.enemy.hp])


## 打满轮数上限仍没 KO 时，必须按兵力收局，不能无限循环。
## 「一局 = 3 回」由下面的承重断言钉死，防止只改常量不更新预期。
func _check_turn_limit() -> void:
	_expect(ArenaScript.TK_MAX_TURNS == 3, "一局卡牌对战应为 3 回，实际 %d" % ArenaScript.TK_MAX_TURNS)
	# 不是把 tk_turn 直接设成上限跳到末尾，而是从第一回连续推进，
	# 证明「打满三回」这条路径真的会在第三回收局。
	a.round_phase = "fight"
	a.round_wins = [0, 0]
	a.tk_turn = 1
	a.player.hp = 70
	a.enemy.hp = 40
	var steps: int = 0
	while a.round_phase != "over" and steps < 10:
		a._finish_taikou_turn()
		steps += 1
	_expect(steps == 3, "应恰好打满 3 回收局，实际 %d 回" % steps)
	_expect(a.tk_turn == 3, "收局时轮数应停在 3，不应自增出越界轮次，实际 %d" % a.tk_turn)
	_expect(a.round_phase == "over", "三回战罢应结束本局")
	_expect(a.round_wins[0] == 1, "兵力高的一方应拿下一局")


func _check_mode_switch() -> void:
	_expect(ArenaScript.BATTLE_MODE == "tactical", "默认使用新战术回合制，传统比牌显式可选")
	_expect(a.battle_mode == "taikou", "传统比牌用例必须显式绑定 taikou")
	# 只验证开关本身可切，不在这里跑实时 _tick_fight（那是另一套自检的职责）。
	a.battle_mode = "realtime"
	_expect(a.battle_mode == "realtime", "应能切回实时兜底模式")
	a.battle_mode = "taikou"

## 怒火槽：只有挨打攒怒、满槽本回升 EX、触发即清空、跨局保留、新一场清零。
func _check_rage() -> void:
	a.round_phase = "fight"
	a.player.reset_for_round(430, 1)
	a.enemy.reset_for_round(850, -1)
	a.tk_player_rage = 0.0
	a.tk_enemy_rage = 0.0

	# 对手赢：玩家挨打攒怒，赢家不攒。
	a.tk_player_result = Rules.evaluate([2, 3, 4])
	a.tk_enemy_result = Rules.evaluate([1, 1, 1])
	a._resolve_taikou()
	_expect(a.tk_winner == "enemy", "构造的牌型应判对手赢")
	_expect(
		a.tk_player_rage == float(a.tk_damage) * Rage.PER_DAMAGE,
		"挨打应按伤害攒怒，实际 %f / dmg=%d" % [a.tk_player_rage, a.tk_damage]
	)
	_expect(a.tk_enemy_rage == 0.0, "赢家不该攒怒")

	# 平局：双方各受 3 点，双方都攒。
	a.tk_player_rage = 0.0
	a.tk_enemy_rage = 0.0
	a.tk_player_result = Rules.evaluate([1, 1, 1])
	a.tk_enemy_result = Rules.evaluate([1, 1, 1])
	a._resolve_taikou()
	_expect(a.tk_winner == "draw", "同分应判平局")
	_expect(
		a.tk_player_rage == 3.0 * Rage.PER_DAMAGE and a.tk_enemy_rage == 3.0 * Rage.PER_DAMAGE,
		"平局双方都该攒怒，实际 %f/%f" % [a.tk_player_rage, a.tk_enemy_rage]
	)

	# 满槽 → 亮牌触发 EX 并清空；未攒满的一方不触发。
	a.tk_player_rage = Rage.MAX
	a.tk_enemy_rage = 0.0
	a.tk_bot = true
	a._do_taikou_reveal()
	_expect(bool(a.tk_player_ex), "满槽亮牌应触发 EX")
	_expect(not bool(a.tk_enemy_ex), "未攒满的一方不该触发 EX")
	_expect(a.tk_player_rage == 0.0, "触发 EX 后怒火应清空")
	_expect(a.tk_player_reveal.size() == 3, "EX 后仍是 3 张牌")
	_expect(
		Rules.compare(a.tk_player_result, Rules.evaluate(a.tk_player_reveal)) == 0,
		"EX 后的判定结果必须与实际显示的 rank 一致"
	)
	a._reset_taikou_turn(false)
	_expect(not bool(a.tk_player_ex), "下一回不该残留 EX 标志")
	a.tk_bot = false

	# 跨局保留，新一场清零。
	a.tk_player_rage = 55.0
	a._start_round()
	_expect(a.tk_player_rage == 55.0, "怒火应跨局保留，实际 %f" % a.tk_player_rage)
	a._start_match()
	_expect(a.tk_player_rage == 0.0, "新一场比赛应清空怒火")
