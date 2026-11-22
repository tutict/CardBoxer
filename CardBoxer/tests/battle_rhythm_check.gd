extends SceneTree
## 回合制 resolve「KOF 式命中节奏」承重自检。
##
## 跑法：godot --headless --path . --script res://tests/battle_rhythm_check.gd
## 退出码 0 = 全过，1 = 有断言失败。
##
## 钉住的不是「常量写对了」，而是：
##   * 节奏纯函数的形状（三角脉冲、击退衰减、相位窗口、淡出）
##   * _resolve_taikou() 真的启动了节奏、平局不启动
##   * 推进节奏**不改 position / hp / 伤害公式**（判定零改动）
##   * visual_shift / visual_tilt 真的被写、且在 recover 段归零

const ArenaScript = preload("res://scripts/arena.gd")
const Rhythm = preload("res://scripts/battle_rhythm.gd")
const Rules = preload("res://scripts/taikou_rules.gd")

var _failures: Array = []
var _total := 0
var a


func _initialize() -> void:
	call_deferred("_run_checks")

func _run_checks() -> void:
	a = ArenaScript.new()
	root.add_child(a)
	if a.player == null:
		a._ready()
	a.round_phase = "fight"

	_check_pure_functions()
	_check_windows()
	_check_resolve_starts_rhythm()
	_check_position_and_damage_untouched()
	_check_visuals_are_applied_and_cleared()

	if _failures.is_empty():
		print("BATTLE RHYTHM CHECK: %d/%d passed" % [_total, _total])
		quit(0)
	else:
		for line: String in _failures:
			print("FAIL: ", line)
		print("BATTLE RHYTHM CHECK: %d/%d failed" % [_failures.size(), _total])
		quit(1)


func _expect(ok: bool, label: String) -> void:
	_total += 1
	if not ok:
		_failures.append(label)


func _fresh() -> void:
	a.round_phase = "fight"
	a.player.reset_for_round(430.0, 1)
	a.enemy.reset_for_round(850.0, -1)
	a.tk_bot = false
	a.tk_player_rage = 0.0
	a.tk_enemy_rage = 0.0
	a.tk_player_ex = false
	a.tk_enemy_ex = false
	a.tk_rhythm_t = -1.0
	a.tk_rhythm_winner = ""
	a.tk_rhythm_hit = false
	a._clear_rhythm_visuals()


func _check_pure_functions() -> void:
	_expect(Rhythm.SPEC_VERSION == "1.0", "规格版本应固定")
	# 注意：phase_at 返回 String，绝不能用 is_equal_approx（只接 float）。
	_expect(is_equal_approx(Rhythm.TOTAL_S, 1.9), "总时长应等于 resolve 阶段 1.9s")
	_expect(is_equal_approx(Rhythm.ATTACK_S + Rhythm.SETTLE_S + Rhythm.RECOVER_S, Rhythm.TOTAL_S),
		"三段时长之和必须等于总时长")
	_expect(is_equal_approx(Rhythm.HIT_AT_S, Rhythm.FRAME_S * 6.0),
		"命中时刻应为离线 ATTACK 内第 6 帧")
	_expect(is_equal_approx(Rhythm.HITSTOP_S, Rhythm.FRAME_S * 3.0),
		"停顿应为离线 3 帧")
	# 三角脉冲：两端为 0，中心为 1，且中心左右对称
	_expect(is_equal_approx(Rhythm.pulse(0.0), 0.0), "pulse(0) 应为 0")
	_expect(is_equal_approx(Rhythm.pulse(0.45), 1.0), "pulse(0.45) 应为 1")
	_expect(is_equal_approx(Rhythm.pulse(0.75), 0.0), "pulse(0.75) 应为 0")
	_expect(is_equal_approx(Rhythm.pulse(0.2), Rhythm.pulse(0.7)),
		"三角脉冲应左右对称")
	_expect(is_equal_approx(Rhythm.press_px(0.45), 110.0), "峰值前压应为 110px")
	_expect(is_equal_approx(Rhythm.knock_px(0.0), 40.0), "击退初值应为 40px")
	_expect(is_equal_approx(Rhythm.knock_px(1.0), 0.0), "击退在攻击窗末应归零")
	_expect(is_equal_approx(Rhythm.tilt_rad(0.0), deg_to_rad(9.0)),
		"后仰初值应为 9 度")
	_expect(is_equal_approx(Rhythm.tilt_rad(1.0), 0.0), "后仰在攻击窗末应归零")
	_expect(Rhythm.press_px(0.1) < Rhythm.press_px(0.45)
		and Rhythm.press_px(0.8) < Rhythm.press_px(0.45),
		"前压必须是脉冲不是整段平移")
	_expect(Rhythm.phase_at(-1.0) == "off", "负时钟应为 off")
	_expect(Rhythm.phase_at(0.5) == "attack", "0.5s 应在 attack")
	_expect(Rhythm.phase_at(1.3) == "settle", "1.3s 应在 settle")
	_expect(Rhythm.phase_at(1.8) == "recover", "1.8s 应在 recover")
	_expect(Rhythm.phase_at(2.0) == "off", "超时应为 off")
	_expect(is_equal_approx(Rhythm.fade_at(0.5), 1.0), "attack 段淡出系数应为 1")
	_expect(is_equal_approx(Rhythm.fade_at(1.68), 0.0), "settle 末应淡到 0")
	_expect(is_equal_approx(Rhythm.fade_at(1.8), 0.0), "recover 段应归零")
	_expect(is_equal_approx(Rhythm.attack_t(2.0), 1.0), "attack_t 应钳到 1")


func _check_windows() -> void:
	_expect(Rhythm.speed_active(0.0) and not Rhythm.speed_active(0.6),
		"速度线应只在攻击窗前半段")
	_expect(not Rhythm.spark_active(0.4) and Rhythm.spark_active(0.5)
		and not Rhythm.spark_active(0.9),
		"星芒应只在命中帧起的 3 帧尾窗")
	_expect(not Rhythm.hit_label_active(0.4) and Rhythm.hit_label_active(0.5)
		and not Rhythm.hit_label_active(0.8),
		"HIT! 标签应只在停顿窗口")
	_expect(is_equal_approx(Rhythm.GAME_GROUND_Y + Rhythm.GAME_SPARK_Y_OFFSET, 390.0),
		"火花高度应按游戏画布重映射到胸口而不是头顶")
	_expect(Rhythm.GAME_HIT_LABEL_POS.y > 300.0,
		"HIT! 标签必须避开 HUD banner 带（y<=280）")


func _check_resolve_starts_rhythm() -> void:
	_fresh()
	a.tk_player_result = Rules.evaluate([9, 9, 9])
	a.tk_enemy_result = Rules.evaluate([2, 5, 8])
	a._resolve_taikou()
	_expect(a.tk_winner == "player", "构造牌型应玩家赢")
	_expect(is_equal_approx(a.tk_rhythm_t, 0.0), "resolve 起点节奏时钟应为 0")
	_expect(a.tk_rhythm_winner == "player", "节奏赢家应为玩家")
	_expect(not a.tk_rhythm_hit, "起点不该已触发停顿")
	_expect(a.tk_phase == "resolve", "仍应进入 resolve 阶段")
	_expect(is_equal_approx(a.tk_phase_time, 0.0), "阶段计时仍从 0 开始")

	_fresh()
	a.tk_player_result = Rules.evaluate([1, 1, 2])
	a.tk_enemy_result = Rules.evaluate([9, 9, 9])
	a._resolve_taikou()
	_expect(a.tk_winner == "enemy", "构造牌型应对手赢")
	_expect(a.tk_rhythm_winner == "enemy", "对手赢时节奏赢家要跟着换")

	_fresh()
	a.tk_player_result = Rules.evaluate([1, 1, 1])
	a.tk_enemy_result = Rules.evaluate([1, 1, 1])
	a._resolve_taikou()
	_expect(a.tk_winner == "draw", "同分应判平局")
	_expect(a.tk_rhythm_t < 0.0 and a.tk_rhythm_winner == "",
		"平局不该激活节奏（保持 P0 对峙）")


func _check_position_and_damage_untouched() -> void:
	_fresh()
	a.tk_player_result = Rules.evaluate([9, 9, 9])
	a.tk_enemy_result = Rules.evaluate([2, 5, 8])
	var expected_damage := Rules.damage_of(a.tk_player_result)
	a._resolve_taikou()
	# a 是 untyped，读它的成员推不出 := 的类型，必须显式标注。
	var px: float = a.player.position.x
	var ex: float = a.enemy.position.x
	var php: int = a.player.hp
	var ehp: int = a.enemy.hp
	_expect(a.tk_damage == expected_damage, "伤害公式不得被节奏层改动")
	_expect(ehp == 100 - expected_damage, "输家掉血应仍等于伤害")
	# 手动推进到命中与击退峰值（不走 _process，避免 hitstop 分支吞帧）
	for i in range(6):
		a._tick_rhythm(0.08)
		a._apply_rhythm_visuals()
	_expect(is_equal_approx(a.player.position.x, px),
		"节奏推进绝不能改玩家 position")
	_expect(is_equal_approx(a.enemy.position.x, ex),
		"节奏推进绝不能改对手 position")
	_expect(a.player.hp == php and a.enemy.hp == ehp,
		"节奏推进绝不能再掉一次血")
	_expect(a.tk_rhythm_hit, "跨过命中时刻应触发一次停顿")
	_expect(a._global_hitstop >= Rhythm.HITSTOP_S - 0.001,
		"命中应复用引擎全局停顿")
	# 再触发一次不应重复设置停顿
	a._global_hitstop = 0.0
	a._tick_rhythm(0.08)
	_expect(is_equal_approx(a._global_hitstop, 0.0),
		"停顿只能触发一次，不能每帧重设")


func _check_visuals_are_applied_and_cleared() -> void:
	_fresh()
	a.tk_player_result = Rules.evaluate([9, 9, 9])
	a.tk_enemy_result = Rules.evaluate([2, 5, 8])
	a._resolve_taikou()
	for i in range(6):
		a._tick_rhythm(0.08)
		a._apply_rhythm_visuals()
	_expect(a.player.visual_shift.x > 0.0,
		"玩家赢时赢家应向 +x 前压")
	_expect(a.enemy.visual_shift.x > 0.0,
		"玩家赢时输家应向 +x 击退")
	_expect(a.enemy.visual_tilt > 0.0,
		"玩家赢时对手后仰应为正角")
	_expect(is_equal_approx(a.player.visual_tilt, 0.0),
		"赢家不该跟着后仰")
	# settle / recover 后必须完全归零
	for i in range(20):
		a._tick_rhythm(0.08)
		a._apply_rhythm_visuals()
	_expect(is_equal_approx(a.player.visual_shift.x, 0.0)
		and is_equal_approx(a.enemy.visual_shift.x, 0.0)
		and is_equal_approx(a.enemy.visual_tilt, 0.0),
		"节奏结束后视觉偏移必须归零")
	_expect(a.tk_rhythm_t < 0.0, "超过总时长应关闭节奏")

	# 对手赢：方向整体反过来
	_fresh()
	a.tk_player_result = Rules.evaluate([1, 1, 2])
	a.tk_enemy_result = Rules.evaluate([9, 9, 9])
	a._resolve_taikou()
	for i in range(6):
		a._tick_rhythm(0.08)
		a._apply_rhythm_visuals()
	_expect(a.enemy.visual_shift.x < 0.0, "对手赢时赢家应向 -x 前压")
	_expect(a.player.visual_shift.x < 0.0, "对手赢时输家应向 -x 击退")
	_expect(a.player.visual_tilt < 0.0, "对手赢时玩家后仰应为负角")

	# 平局：P0 对峙，无任何节奏位移
	_fresh()
	a.tk_player_result = Rules.evaluate([1, 1, 1])
	a.tk_enemy_result = Rules.evaluate([1, 1, 1])
	a._resolve_taikou()
	a._apply_rhythm_visuals()
	_expect(is_equal_approx(a.player.visual_shift.x, 0.0)
		and is_equal_approx(a.enemy.visual_shift.x, 0.0),
		"平局不该出现任何前压/击退")
