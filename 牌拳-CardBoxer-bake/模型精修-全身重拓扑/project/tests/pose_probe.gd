extends SceneTree
## 姿势探针：证明 fighter 实际画出来的关节 == 表里那一帧。
##
## 跑法（游戏目录下）：
##   godot --headless --path . --script res://tests/pose_probe.gd
##
## 和 motion_check 的分工：那个证明「表 → 取帧函数」没错，这个证明「取帧 → 画出来的
## 关节」没错。后者的帧号**不用被测函数**算 —— 它来自「每 tick 一帧」这个事实
## （游戏 60fps，一张牌 N 帧就是 N 次 tick），所以这一步同时也在检验浮点取整没跑偏。

const Defs = preload("res://scripts/card_data.gd")
const FighterScript = preload("res://scripts/fighter.gd")
const PATH := "res://data/card_motion.json"

## 表以「无呼吸站姿」为基准，fighter 会补回呼吸位移；这里用同一份规格复算期望值。
const TOL := 1e-4
const JOINTS := [
	"hip", "shoulder", "head",
	"f_elbow", "f_hand", "b_elbow", "b_hand",
	"f_knee", "f_foot", "b_knee", "b_foot",
]
#: 跟着呼吸上下动的关节：躯干三点 + 四条臂。腿钉在地面上，不动。
const BREATH_JOINTS := [
	"hip", "shoulder", "head",
	"f_elbow", "f_hand", "b_elbow", "b_hand",
]

var _fail := 0
var _frames := 0
var _values := 0


func _init() -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(PATH))
	if typeof(parsed) != TYPE_DICTIONARY:
		print("FAIL: 表读不出来")
		quit(1)
		return
	var cards: Dictionary = (parsed as Dictionary).get("cards", {})
	var motions: Dictionary = (parsed as Dictionary).get("motions", {})

	var report: Array = []
	for id: String in Defs.CARDS:
		if not cards.has(id):
			_fail += 1
			report.append("FAIL %-9s 无表" % id)
			continue
		report.append(_probe(id, cards[id]))

	# 站架一致性：每张牌的帧 0 是起手姿势、末帧是收招归位姿势，而待机画的是同一副
	# 站架。三处一旦对不上，每一招的起手和收招都会跳一下 —— 这是这套接线里最容易
	# 悄悄坏掉的一条，所以拆成两半查：表内部自洽 + 待机与表一致。
	var stance_ok := _check_stance(cards, motions)
	if not stance_ok:
		_fail += 1

	for line in report:
		print(line)
	# 假通过闸门：一帧都没对照上却报 PASS，比没有这个探针更坏。
	if _frames == 0:
		_fail += 1
		print("FAIL 闸门: 一帧都没对照到（fighter 没构造成功或没出招）")
	print("")
	print("逐帧对照 %d 帧 / %d 个关节值，失败 %d 项" % [_frames, _values, _fail])
	print("POSE PROBE: " + ("PASS" if _fail == 0 else "FAIL"))
	quit(0 if _fail == 0 else 1)


## 待机画出来的姿势 vs 表里的站架。呼吸位移要减掉（表以无呼吸站姿为基准）。
## 同时查表内部自洽：所有牌的帧 0 必须相同（否则起手姿势随牌变化），所有牌和受击
## 反应的末帧必须回到帧 0（否则收招/恢复接待机时会跳）。
func _check_stance(cards: Dictionary, motions: Dictionary) -> bool:
	var f: Node2D = FighterScript.new()
	f.is_player = true
	f.facing = 1
	root.add_child(f)
	f.tick(Defs.FRAME, 0.0, true)
	var pose: Dictionary = f._build_pose()
	var breathe: float = sin(f._breath * 2.4) * 3.0
	var raw: Dictionary = (cards["recover"]["track"] as Array)[0]
	var worst := 0.0
	for key: String in JOINTS:
		var want: Array = raw[key]
		var dy := breathe if BREATH_JOINTS.has(key) else 0.0
		var exp := Vector2(float(want[0]), float(want[1]) + dy)
		var got: Vector2 = pose[key]
		worst = maxf(worst, maxf(absf(got.x - exp.x), absf(got.y - exp.y)))
	# 反向对照：把 v1 的旧站架（髋 -92 / 膝 -46 / 后脚 -34）拿来比，必须差得远 ——
	# 否则这条检查对「待机没跟着换站架」这个错误是瞎的。
	var stale := 0.0
	stale = maxf(stale, absf(float((raw["hip"] as Array)[1]) - (-92.0)))
	stale = maxf(stale, absf(float((raw["f_knee"] as Array)[1]) - (-46.0)))
	stale = maxf(stale, absf(float((raw["b_foot"] as Array)[0]) - (-34.0)))

	# 表内部：起手帧族内一致 + 末帧归位。判据 1.5 px —— 实测上限 1.0 px（筋长取整 +
	# 解算余量），留半像素的余量而不是卡在边界上；真正的收招没归位是 5 px 起。
	var drift := 0.0
	var who := "无"
	for id: String in cards:
		var track: Array = cards[id]["track"]
		var d0 := _gap(track[0], raw)
		var d1 := _gap(track[track.size() - 1], raw)
		if d0 > drift:
			drift = d0
			who = "%s 帧0" % id
		if d1 > drift:
			drift = d1
			who = "%s 末帧" % id
	for name: String in motions:
		var track: Array = motions[name]["track"]
		var d0 := _gap(track[0], raw)
		var d1 := _gap(track[track.size() - 1], raw)
		if d0 > drift:
			drift = d0
			who = "%s 首帧" % name
		if d1 > drift:
			drift = d1
			who = "%s 末帧" % name

	var ok := worst <= 0.5 and stale >= 5.0 and drift <= 1.5
	print("%s 站架: 待机 vs 表 %.3f px（<=0.5）；与 v1 旧站架 %.1f px（>=5）；表内起收招最大漂移 %.3f px @%s（<=1.5）" % [
		"OK " if ok else "FAIL", worst, stale, drift, who])
	f.queue_free()
	return ok


## 两组关节的最大单轴差。
func _gap(a: Dictionary, b: Dictionary) -> float:
	var w := 0.0
	for key: String in JOINTS:
		var x: Array = a[key]
		var y: Array = b[key]
		w = maxf(w, maxf(absf(float(x[0]) - float(y[0])), absf(float(x[1]) - float(y[1]))))
	return w


func _probe(id: String, entry: Dictionary) -> String:
	var track: Array = entry["track"]
	var split: Array = entry["split"]
	var w := int(split[0])
	var a := int(split[1])
	var r := int(split[2])
	var total := w + a + r

	var f: Node2D = FighterScript.new()
	if f == null:
		_fail += 1
		return "FAIL %-9s fighter 构造失败" % id
	f.is_player = true
	f.facing = 1
	f.meter = 5.0
	root.add_child(f)
	if not f.play_card(id):
		f.queue_free()
		_fail += 1
		return "FAIL %-9s 出牌失败（气不够/不可行动）" % id

	var ticks := {"windup": 0, "active": 0, "recover": 0}
	var worst := 0.0
	var bad: Array = []
	var drawn := 0
	for _i in range(total):
		f.tick(Defs.FRAME, 0.0, true)
		# 后摇走完 _end_action() 会把 _action_phase 清空，那之后画的是待机姿势。
		if String(f._action_phase) == "":
			break
		var phase: String = f._action_phase
		ticks[phase] = int(ticks[phase]) + 1
		var n := int(ticks[phase])
		var idx := 0
		match phase:
			"windup":
				# 出牌那次调用不画；之后第一 tick 已经是 progress=1/N，
				# 所以表第 1 帧（静止帧）不画，前摇从第 2 帧起。
				idx = mini(n, w - 1)
			"active":
				# active 为 0 的牌（位移/守御）游戏当帧略过，画面停在前摇末帧。
				idx = (w - 1) if a <= 0 else (w + mini(n - 1, a - 1))
			_:
				# 切相那一次就已经以 progress=0 画过一帧，所以从 n-1 起算。
				idx = w + a + mini(n - 1, r - 1)
		if idx >= track.size():
			bad.append("%s 帧号越界 idx=%d size=%d" % [phase, idx, track.size()])
			break

		var pose: Dictionary = f._build_pose()
		var raw: Dictionary = track[idx]
		var breathe: float = sin(f._breath * 2.4) * 3.0
		# 这里曾经要减掉侧闪在表之外叠的那一层整体平移。那一层已经删了
		# （`position.x` 与 7 个关节各挪一次，画面走 132 px 而判定只走 66 px，
		# 前腿还被拉到 1.49 倍），所以探针不再需要对账项 —— 表就是画面的全部。
		for key: String in JOINTS:
			var want: Array = raw[key]
			var dy := breathe if BREATH_JOINTS.has(key) else 0.0
			var exp := Vector2(float(want[0]), float(want[1]) + dy)
			var got: Vector2 = pose[key]
			_values += 1
			worst = maxf(worst, maxf(absf(got.x - exp.x), absf(got.y - exp.y)))
			if absf(got.x - exp.x) > TOL or absf(got.y - exp.y) > TOL:
				bad.append("f%d %s got%s exp%s" % [idx + 1, key, str(got), str(exp)])
		if absf(float(pose["lean"]) - float(raw["lean"])) > TOL:
			bad.append("f%d lean got%.3f exp%.3f" % [idx + 1, float(pose["lean"]), float(raw["lean"])])
		drawn += 1
		_frames += 1

	f.queue_free()
	if drawn == 0:
		_fail += 1
		return "FAIL %-9s 一帧都没画出来" % id
	if bad.is_empty():
		return "OK %-9s %2d 帧，最大误差 %.6f px" % [id, drawn, worst]
	_fail += 1
	return "FAIL %-9s %d 处: %s" % [id, bad.size(), " | ".join(bad.slice(0, 4))]
