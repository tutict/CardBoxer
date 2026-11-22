extends SceneTree
## 回合制合战「P0 动作接线」承重自检。
##
## 跑法：godot --headless --path . --script res://tests/battle_motion_p0_check.gd
## 退出码 0 = 全过，1 = 有断言失败。
##
## 钉住的不是「常量写对了」，而是接线真的生效：
##   * 亮牌阶段只播 focus、不记录赢家动作、不掉血、_visual_only 为真；
##   * 三档牌型各自把指定动作交给赢家、把指定受击档交给输家；
##   * 平局不播攻击；新回清空动作状态；
##   * 旧形态 perform_visual(String(tk_*_ids[0])) 已退役；
##   * 所有引用的 reuse 资产在 combat_motion_3d.json 里真实存在，
##     而 spec 标 new: 的 hit_crush 不许被当成已烘。
##
## 伤害数值仍由 Rules.damage_of() 决定，这里只证明「接线没改公式」。

const ArenaScript = preload("res://scripts/arena.gd")
const MotionP0 = preload("res://scripts/battle_motion_p0.gd")
const Rules = preload("res://scripts/taikou_rules.gd")
const NativeMotion = preload("res://scripts/native_motion.gd")

var _failures: Array = []
var _total := 0
var a


func _initialize() -> void:
	call_deferred("_run_checks")

func _run_checks() -> void:
	a = ArenaScript.new()
	root.add_child(a)
	# SceneTree._initialize() 阶段主循环未起，add_child 不触发 _ready()；
	# 显式跑一次，否则 player / enemy 为 Nil，断言全是假红。
	if a.player == null:
		a._ready()
	a.round_phase = "fight"

	_check_spec_constants()
	_check_assets_exist()
	_check_source_shape()
	_check_reveal_is_ceremony()
	_check_bindings_three_types()
	_check_enemy_winner_branch()
	_check_draw()
	_check_reset_clears()

	if _failures.is_empty():
		print("BATTLE MOTION P0 CHECK: %d/%d passed" % [_total, _total])
		quit(0)
	else:
		for line: String in _failures:
			print("FAIL: ", line)
		print("BATTLE MOTION P0 CHECK: %d/%d failed" % [_failures.size(), _total])
		quit(1)


func _expect(ok: bool, label: String) -> void:
	_total += 1
	if not ok:
		_failures.append(label)


func _fresh() -> void:
	a.round_phase = "fight"
	a.player.reset_for_round(430.0, 1)
	a.enemy.reset_for_round(850.0, -1)
	a.tk_player_rage = 0.0
	a.tk_enemy_rage = 0.0
	a.tk_player_ex = false
	a.tk_enemy_ex = false
	a.tk_bot = false


## 与 combat-motion-design/battle_motion_spec.json 的 card_type_binding 逐项对齐。
## 跨工程的 JSON ↔ GDScript 一致性另由 motion-integration-p0/verify_p0.py 源码扫描证明。
func _check_spec_constants() -> void:
	var expected := {
		"triple": {"winner_card": "wave", "react": "hit_crush", "extra": "super", "label": "气功波"},
		"sequence": {"winner_card": "cross", "react": "hit_heavy", "extra": "launch", "label": "交叉反击"},
		"scatter": {"winner_card": "jab", "react": "hit_light", "extra": "", "label": "刺拳"},
	}
	for t: String in expected:
		var b: Dictionary = MotionP0.binding_for(t)
		for k: String in expected[t]:
			_expect(String(b.get(k, "<missing>")) == String(expected[t][k]),
				"%s.%s 应为 %s，实际 %s" % [t, k, expected[t][k], b.get(k, "<missing>")])
	_expect(MotionP0.REVEAL_CARD == "focus", "亮牌仪式应复用 focus")
	_expect(String(MotionP0.DRAW["extra"]) == "", "平局不该带受击 extra")
	_expect(String(MotionP0.DRAW["react"]) == "hit_light", "平局受击档应为 hit_light")
	_expect(MotionP0.label_of("") == "对峙", "平局动作标签应为对峙")
	_expect(MotionP0.hit_extra("triple") == "super", "三同应走 super 档")
	_expect(MotionP0.winner_card("sequence") == "cross", "三连应播 cross")
	_expect(MotionP0.SPEC_VERSION == "1.0-p0", "规格版本应固定")


func _check_assets_exist() -> void:
	var library = NativeMotion.new()
	_expect(library.load_data(), "native animation data loads")
	for role: String in ["player", "foe"]:
		for id: String in ["stance", "focus", "jab", "cross", "wave", "hit_light", "hit_heavy", "block"]:
			_expect(library.clip_frames(role, id) > 0, "%s has the reused native clip %s" % [role, id])
			var pose: Dictionary = library.sample(role, id, 0.0)
			_expect(not pose.is_empty() and not pose.has("error"), "%s clip %s produces a native pose" % [role, id])
		_expect(library.clip_frames(role, "hit_crush") == 0, "unbaked hit_crush is not claimed as a native clip")
	for asset: String in MotionP0.reuse_assets():
		_expect(asset in ["focus", "jab", "cross", "wave", "hit_light", "hit_heavy", "stance"], "reuse assets must not include unbaked clips: " + asset)

## 源码形态守卫：钉真实接线，不钉注释里也会出现的词。
func _check_source_shape() -> void:
	var src := FileAccess.get_file_as_string("res://scripts/arena.gd")
	_expect(not ("perform_visual(String(tk_player_ids[0]))" in src),
		"G1 旧形态：亮牌播第一张牌必须退役")
	_expect(not ("perform_visual(String(tk_enemy_ids[0]))" in src),
		"G1 旧形态：对手侧也要退役")
	_expect("MotionP0.binding_for(winner_type)" in src,
		"P2 动作必须由赢家牌型绑定驱动")
	_expect("MotionP0.REVEAL_CARD" in src, "P1 亮牌仪式必须走 REVEAL_CARD")
	_expect("apply_hit(tk_damage, \"taikou\", tk_motion_extra, false)" in src,
		"G4 apply_hit 必须传分档 extra")
	_expect("apply_hit(3, \"taikou\", tk_motion_extra, false)" in src,
		"平局 apply_hit 也必须走同一条分档口径")
	_expect(src.count("tk_motion_id = \"\"") >= 2,
		"亮牌/平局/重置至少要清空两次动作状态")
	var hud_src := FileAccess.get_file_as_string("res://scripts/hud.gd")
	_expect("arena.tk_motion_id" in hud_src, "HUD 必须显示本回动作")


func _check_reveal_is_ceremony() -> void:
	_fresh()
	a.tk_bot = true
	a._do_taikou_reveal()
	_expect(a.tk_phase == "reveal", "应进入亮牌阶段")
	_expect(a.tk_motion_id == "", "P1 亮牌阶段不该记录赢家动作")
	_expect(String(a.player._action.get("id", "")) == "focus",
		"玩家亮牌应播 focus，实际 %s" % a.player._action.get("id", ""))
	_expect(String(a.enemy._action.get("id", "")) == "focus",
		"对手亮牌应播 focus，实际 %s" % a.enemy._action.get("id", ""))
	_expect(a.player.hp == 100 and a.enemy.hp == 100, "亮牌阶段绝不能掉血")
	_expect(bool(a.player._visual_only) and bool(a.enemy._visual_only),
		"亮牌两侧必须处于纯表演状态")
	a.tk_bot = false


func _check_bindings_three_types() -> void:
	var cases := {
		"triple": {"ranks": [9, 9, 9], "foe": [2, 5, 8], "stun": 0.75},
		"sequence": {"ranks": [4, 5, 6], "foe": [2, 5, 8], "stun": 0.42},
		"scatter": {"ranks": [2, 5, 8], "foe": [1, 1, 2], "stun": 0.26},
	}
	for t: String in cases:
		_fresh()
		var c: Dictionary = cases[t]
		a.tk_player_result = Rules.evaluate(c["ranks"])
		a.tk_enemy_result = Rules.evaluate(c["foe"])
		_expect(Rules.compare(a.tk_player_result, a.tk_enemy_result) > 0,
			"%s 用例必须构造成玩家赢" % t)
		a._resolve_taikou()
		var b: Dictionary = MotionP0.binding_for(t)
		_expect(a.tk_winner == "player", "%s 用例赢家应为玩家" % t)
		_expect(a.tk_motion_id == String(b["winner_card"]),
			"%s 应播 %s，实际 %s" % [t, b["winner_card"], a.tk_motion_id])
		_expect(a.tk_motion_extra == String(b["extra"]),
			"%s 的 extra 应为 %s，实际 %s" % [t, b["extra"], a.tk_motion_extra])
		_expect(a.tk_react_id == String(b["react"]),
			"%s 的 react 应为 %s" % [t, b["react"]])
		_expect(a.tk_damage == Rules.damage_of(a.tk_player_result),
			"接线不该改伤害公式")
		_expect(String(a.player._action.get("id", "")) == a.tk_motion_id,
			"%s 赢家必须真的在播该动作" % t)
		_expect(is_equal_approx(float(a.enemy._stun_duration), float(c["stun"])),
			"%s 输家硬直应为 %.2fs，实际 %.2f" % [t, c["stun"], a.enemy._stun_duration])
		_expect(a.enemy.hp == 100 - a.tk_damage, "%s 输家掉血应等于伤害" % t)
		_expect(a.player.hp == 100, "%s 赢家不该掉血" % t)


## 对手赢时动作要落在对手身上，不能永远播玩家侧。
func _check_enemy_winner_branch() -> void:
	_fresh()
	a.tk_player_result = Rules.evaluate([1, 1, 2])
	a.tk_enemy_result = Rules.evaluate([9, 9, 9])
	a._resolve_taikou()
	_expect(a.tk_winner == "enemy", "构造的牌型应判对手赢")
	_expect(a.tk_motion_id == "wave", "对手三同应播 wave")
	_expect(a.tk_motion_extra == "super", "对手三同应走 super 档")
	_expect(String(a.enemy._action.get("id", "")) == "wave", "对手必须真的在播 wave")
	_expect(is_equal_approx(float(a.player._stun_duration), 0.75),
		"玩家输家硬直应为 0.75s")
	_expect(String(a.player._action.get("id", "")) != "wave",
		"输家不该同时播赢家动作")


func _check_draw() -> void:
	_fresh()
	a.tk_player_result = Rules.evaluate([1, 1, 1])
	a.tk_enemy_result = Rules.evaluate([1, 1, 1])
	a._resolve_taikou()
	_expect(a.tk_winner == "draw", "同分应判平局")
	_expect(a.tk_motion_id == "", "P3 平局不该播赢家攻击")
	_expect(a.tk_motion_extra == "", "平局不该带受击 extra")
	_expect(a.tk_react_id == "hit_light", "平局受击档应为 hit_light")
	_expect(a.player.hp == 97 and a.enemy.hp == 97, "平局双方各受 3 点")
	_expect(is_equal_approx(float(a.player._stun_duration), 0.26)
		and is_equal_approx(float(a.enemy._stun_duration), 0.26),
		"平局双方都走默认 0.26s 硬直")


func _check_reset_clears() -> void:
	a._reset_taikou_turn(false)
	_expect(a.tk_motion_id == "" and a.tk_motion_extra == ""
		and a.tk_react_id == "" and a.tk_motion_label == "",
		"新一轮必须清空上一回的动作状态")
