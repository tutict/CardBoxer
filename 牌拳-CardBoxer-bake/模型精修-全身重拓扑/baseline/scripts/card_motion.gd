class_name CardMotion
extends RefCounted
## 招式关节表：读 `res://data/card_motion.json`，按「相位 + 相位内进度」取出整副关节。
##
## 表是在 Blender 里做的：每张牌按游戏自己的 60fps 帧数逐帧烘一遍，帧数就是
## card_data 的 windup/active/recover（12 张逐卡核对过，见 split），所以
## 「第几帧」天然和伤害结算那一刻对齐 —— 不需要再插值去猜。
##
## 数据是**游戏像素坐标**：原点在脚下，+x 正前方，-y 向上。换向只翻 x
## （lean 也跟着翻），和 fighter.gd 里手写姿势的 `* f` 口径一致。
##
## 取不到表（文件缺失/该卡没烘）时返回空字典，调用方退回手写姿势 —— 这是
## 一个纯增量替换，不改变任何结算逻辑。

const PATH := "res://data/card_motion.json"

## 见 `_frame_index()`：抵消浮点除法回乘的负误差。
const _EPS := 1e-6

## 与 fighter.gd `_build_pose()` 返回的键一一对应。
const JOINTS := [
	"hip", "shoulder", "head",
	"f_elbow", "f_hand", "b_elbow", "b_hand",
	"f_knee", "f_foot", "b_knee", "b_foot",
]

static var _tracks: Dictionary = {}
static var _splits: Dictionary = {}
static var _reacts: Dictionary = {}
static var _tried := false


## 表是否载入成功。调试与自检用；正常绘制不需要先查这个。
static func available() -> bool:
	_ensure()
	return not _tracks.is_empty()


static func has_card(id: String) -> bool:
	_ensure()
	return _tracks.has(id)


static func _ensure() -> void:
	if _tried:
		return
	_tried = true
	if not FileAccess.file_exists(PATH):
		push_warning("card_motion.json 缺失，退回手写姿势：%s" % PATH)
		return
	var text := FileAccess.get_file_as_string(PATH)
	var parsed: Variant = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		push_warning("card_motion.json 解析失败，退回手写姿势")
		return
	var cards: Variant = (parsed as Dictionary).get("cards", {})
	if typeof(cards) != TYPE_DICTIONARY:
		push_warning("card_motion.json 没有 cards，退回手写姿势")
		return
	for id: String in (cards as Dictionary):
		var entry: Dictionary = (cards as Dictionary)[id]
		var track: Array = entry.get("track", [])
		var split: Array = entry.get("split", [])
		if track.is_empty() or split.size() != 3:
			continue
		_tracks[id] = track
		_splits[id] = split

	# 受击反应不是「牌」，没有相位可切：整条轨道按硬直时长的归一化进度播放，
	# 所以任何硬直长度都能正好在恢复控制权那一帧回到站架。
	var motions: Variant = (parsed as Dictionary).get("motions", {})
	if typeof(motions) == TYPE_DICTIONARY:
		for name: String in (motions as Dictionary):
			var entry: Dictionary = (motions as Dictionary)[name]
			var track: Array = entry.get("track", [])
			if not track.is_empty():
				_reacts[name] = track


## 某一相位内的第几帧。进度是 0..1，除以相位帧数再取整即「这一帧画哪张图」；
## 钳在相位内，绝不跨到下一个相位去取，否则前摇的最后一帧会借到出招姿势。
##
## `_EPS` 不是保险丝而是必需：进度是 `_phase_time / span` 两个浮点相除，
## `7 帧里的第 3 帧` 会算成 0.42857142857142855，乘回 7 得 2.9999999999999996，
## 直接 int() 会提前一帧退回去 —— 表现为某张图被画两次、下一张被跳过。
static func _frame_index(split: Array, phase: String, progress: float) -> int:
	var w := int(split[0])
	var a := int(split[1])
	var r := int(split[2])
	var t := clampf(progress, 0.0, 1.0)
	match phase:
		"windup":
			return clampi(int(t * float(w) + _EPS), 0, maxi(w - 1, 0))
		"active":
			# active 为 0 的牌（位移/守御）游戏会当帧跳过，真进来了就贴在前摇末帧上。
			if a <= 0:
				return clampi(w - 1, 0, w - 1)
			return w + clampi(int(t * float(a) + _EPS), 0, a - 1)
		_:
			if r <= 0:
				return maxi(0, w + a - 1)
			return w + a + clampi(int(t * float(r) + _EPS), 0, r - 1)


## 取一帧关节。返回 {"hip": Vector2, ..., "lean": float}；取不到返回 {}。
## `facing` 用 ±1 传入，x 与 lean 一并翻转。
static func sample(id: String, phase: String, progress: float, facing: float) -> Dictionary:
	_ensure()
	if not _tracks.has(id):
		return {}
	var track: Array = _tracks[id]
	var split: Array = _splits[id]
	var idx := _frame_index(split, phase, progress)
	if idx < 0 or idx >= track.size():
		return {}
	return _pose_at(track[idx], facing)


## 受击反应的一帧。`t01` 是硬直内的归一化进度（0 = 刚被打中，1 = 恢复控制权）。
## 首尾帧都是站架，所以接回待机不会有跳变。
static func sample_react(name: String, t01: float, facing: float) -> Dictionary:
	_ensure()
	if not _reacts.has(name):
		return {}
	var track: Array = _reacts[name]
	var last := track.size() - 1
	var idx := clampi(int(clampf(t01, 0.0, 1.0) * float(last) + 0.5), 0, last)
	return _pose_at(track[idx], facing)


static func _pose_at(raw: Dictionary, facing: float) -> Dictionary:
	var out := {}
	for key: String in JOINTS:
		var v: Variant = raw.get(key)
		if typeof(v) != TYPE_ARRAY:
			return {}
		var arr: Array = v
		if arr.size() != 2:
			return {}
		out[key] = Vector2(float(arr[0]) * facing, float(arr[1]))
	out["lean"] = float(raw.get("lean", 0.0)) * facing
	return out
