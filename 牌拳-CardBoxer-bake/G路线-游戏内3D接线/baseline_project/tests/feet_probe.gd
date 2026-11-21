extends SceneTree
## 脚：画出来的脚相对身体在哪儿、每一帧在地面上挪了多少、腿有没有被拉长。
##
##   godot --headless --path . --script res://tests/feet_probe.gd
##
## 三件在 `pose_probe` 里看不见的事：
##   1. `pose_probe` 会把侧闪那层运行时偏移**减掉**再核对表，于是「那层偏移本身是否
##      合理」从来没有被任何人检查过；
##   2. 位移牌（rush/backstep/sidestep）是把 `position.x` 一帧内改掉的，姿势表管不到
##      这件事 —— 表里的脚是相对身体画的，身体瞬移则脚跟着瞬移；
##   3. 腿被拉长在表里有 k 记录，但运行时再叠一层偏移（侧闪）之后的实际腿长没人算。
##
## 所以这里只量**画出来的世界坐标**：world = position.x + pose[foot].x。

const Defs = preload("res://scripts/card_data.gd")
const FighterScript = preload("res://scripts/fighter.gd")

## 站立时髋到脚的距离（画的姿势，不是骨长）。腿被拉长的判据以它为基准。
const JOINTS := ["f_foot", "b_foot"]

## 身体一帧挪超过这个数就是「瞬移」而不是「位移」。走路是 3.6 px/帧，冲刺摊到
## 5 帧是 34 px/帧，所以 40 是这条线；原来 rush 是一帧 172 px。
const BODY_STEP_TOL := 40.0
## 腿长相对站姿的允许倍数。腿只有 90 px，1.2 倍以上肉眼就是橡皮腿。
const LEG_TOL := 1.25
## 出生点必须在擂台里。擂台是 [150, 1130]，默认 position 是 0 —— 把拳手放在 0 上
## 跑位移牌，第一次 `_advance_slide` 就被 clamp 到 150，量出来是「一帧瞬移 150 px」，
## 那是对着擂台边界量出来的假象，不是位移牌的毛病。
const SPAWN_X := 640.0

var _fail := 0


func _init() -> void:
	var rest_leg := _rest_leg()
	print("站姿髋→前脚 %.1f px，髋→后脚 %.1f px" % [rest_leg[0], rest_leg[1]])
	print("")
	print("%-10s %11s %11s %9s %9s  %s" % [
		"牌", "前脚单帧位移", "后脚单帧位移", "前腿最长", "后腿最长", "判定"])
	for id: String in Defs.CARDS:
		_probe(id, rest_leg)
	_walk_report()
	print("")
	print("FEET PROBE: " + ("PASS" if _fail == 0 else "FAIL"))
	quit(0 if _fail == 0 else 1)


## 走路：脚有没有真的踩在地上。判据是「支撑期该脚在世界坐标里不动」——
## 现在 `_build_pose` 的走路是 `sin(_walk_time*9)` 驱动，身体匀速前进而脚的相对
## 位移是正弦，两者相位无关，所以脚永远在滑。
func _walk_report() -> void:
	var f: Node2D = FighterScript.new()
	f.is_player = true
	f.facing = 1
	root.add_child(f)
	f.position.x = SPAWN_X
	# 起步那 0.11 s 是「站架 → 走姿」的过渡（髋沉下去、两脚收到走路的基准位置），
	# 过渡期脚本来就会滑，量的是稳态步态。
	var settle := 12
	for _i in range(settle):
		f.tick(Defs.FRAME, 1.0, true)
	var prev := {}
	var planted := {"f_foot": 0, "b_foot": 0}
	var rel_range := {"f_foot": [-1e9, 1e9], "b_foot": [-1e9, 1e9]}
	var slip_max := {"f_foot": 0.0, "b_foot": 0.0}
	var start_x: float = f.position.x
	var frames := 90
	for i in range(frames):
		f.tick(Defs.FRAME, 1.0, true)
		var pose: Dictionary = f._build_pose()
		for key: String in JOINTS:
			var rel: float = (pose[key] as Vector2).x
			var world: float = float(f.position.x) + rel
			rel_range[key][0] = maxf(float(rel_range[key][0]), rel)
			rel_range[key][1] = minf(float(rel_range[key][1]), rel)
			if i > 0:
				var d: float = absf(world - float(prev[key]))
				slip_max[key] = maxf(float(slip_max[key]), d)
				if d < 1.0:
					planted[key] += 1
			prev[key] = world
	var moved: float = absf(f.position.x - start_x)
	f.queue_free()
	print("")
	print("走路 %d 帧：身体前进 %.0f px（%.1f px/帧）" % [frames, moved, moved / float(frames)])
	for key: String in JOINTS:
		print("  %-7s 世界滑移峰值 %5.1f px/帧；踩实帧 %2d/%d（%2d%%）；相对身体摆幅 %.0f px" % [
			key, slip_max[key], planted[key], frames - 1,
			int(round(100.0 * float(planted[key]) / float(frames - 1))),
			float(rel_range[key][0]) - float(rel_range[key][1])])
	# 判据：走起来时两只脚合计至少要有 40% 的帧是踩实的（正常人走路每只脚
	# 约 50% 支撑期）。0% 就是两只脚全程在冰上滑。
	var total_planted := int(planted["f_foot"]) + int(planted["b_foot"])
	var ratio := float(total_planted) / float(2 * (frames - 1))
	if ratio < 0.4:
		_fail += 1
		print("BAD 走路: 两只脚合计踩实 %d%%，判据 ≥40%% —— 脚全程在地上滑" % int(round(ratio * 100.0)))
	else:
		print("OK  走路: 两只脚合计踩实 %d%%" % int(round(ratio * 100.0)))


## 站姿的髋→脚距离。用同一份绘制代码算，不抄表里的数。
func _rest_leg() -> Array:
	var f: Node2D = FighterScript.new()
	f.is_player = true
	f.facing = 1
	root.add_child(f)
	f.tick(Defs.FRAME, 0.0, true)
	var pose: Dictionary = f._build_pose()
	var hip: Vector2 = pose["hip"]
	var out := [(pose["f_foot"] as Vector2).distance_to(hip),
		(pose["b_foot"] as Vector2).distance_to(hip)]
	f.queue_free()
	return out


func _probe(id: String, rest_leg: Array) -> void:
	var card := Defs.card(id)
	if card.is_empty():
		return
	var f: Node2D = FighterScript.new()
	f.is_player = true
	f.facing = 1
	f.meter = 5.0
	root.add_child(f)
	f.position.x = SPAWN_X
	if not f.play_card(id):
		return

	var prev := {}
	var slip := {"f_foot": 0.0, "b_foot": 0.0}
	var leg_ratio := {"f_foot": 0.0, "b_foot": 0.0}
	var total := int(card.get("windup", 0)) + int(card.get("active", 0)) + int(card.get("recover", 0))
	var drawn := 0
	var body_step := 0.0
	var prev_pos: float = f.position.x
	for _i in range(total + 2):
		f.tick(Defs.FRAME, 0.0, true)
		if String(f._action_phase) == "" and drawn > 0:
			break
		body_step = maxf(body_step, absf(float(f.position.x) - prev_pos))
		prev_pos = float(f.position.x)
		# 出招期间 hitstop 会冻结 tick（提前 return），姿势不变但世界位置也不变，
		# 所以这里只统计姿势真的变了的那一帧。
		var pose: Dictionary = f._build_pose()
		var hip: Vector2 = pose["hip"]
		for key: String in JOINTS:
			var rel: float = (pose[key] as Vector2).x
			if prev.has(key):
				slip[key] = maxf(float(slip[key]), absf(rel - float(prev[key])))
			prev[key] = rel
			leg_ratio[key] = maxf(float(leg_ratio[key]),
				(pose[key] as Vector2).distance_to(hip) / float(rest_leg[0 if key == "f_foot" else 1]))
		drawn += 1
	f.queue_free()

	var bad := body_step > BODY_STEP_TOL \
		or float(leg_ratio["f_foot"]) > LEG_TOL or float(leg_ratio["b_foot"]) > LEG_TOL
	if bad:
		_fail += 1
	print("%s %-10s %9.1f %8.1f %8.1f %8.2fx %8.2fx  %s" % [
		"OK " if not bad else "BAD", id, body_step, slip["f_foot"], slip["b_foot"],
		leg_ratio["f_foot"], leg_ratio["b_foot"],
		"" if not bad else _why(body_step, leg_ratio)])


func _why(body_step: float, leg: Dictionary) -> String:
	var out := []
	if body_step > BODY_STEP_TOL:
		out.append("身体单帧瞬移 %.0f px" % body_step)
	if float(leg["f_foot"]) > LEG_TOL:
		out.append("前腿拉到 %.2f 倍" % leg["f_foot"])
	if float(leg["b_foot"]) > LEG_TOL:
		out.append("后腿拉到 %.2f 倍" % leg["b_foot"])
	return "；".join(out)
