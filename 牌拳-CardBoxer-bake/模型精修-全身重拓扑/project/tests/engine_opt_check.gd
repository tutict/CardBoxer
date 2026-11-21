extends SceneTree
## 引擎优化（裁掉被不透明贴图完全覆盖的死绘制）承重自检。
##
## 跑法：godot --headless --path . --script res://tests/engine_opt_check.gd
## 退出码 0 = 全过，1 = 有断言失败。
##
## 钉的是形态不是词：所有源码计数都排除注释行与行内注释，
## 避免「注释还在、代码已删/已改」造成假绿。

const Backdrop = preload("res://background/arena.png")

var _failures: Array = []
var _total := 0
var src := ""


func _expect(cond: bool, label: String) -> void:
	_total += 1
	if not cond:
		_failures.append(label)


func _real_count(form: String) -> int:
	var n := 0
	for ln in src.split("\n"):
		if ln.strip_edges().begins_with("#"):
			continue
		var i := ln.find(form)
		if i < 0:
			continue
		if ln.substr(0, i).find("#") >= 0:
			continue
		n += 1
	return n


func _backdrop_body() -> String:
	var i := src.find("func _draw_backdrop() -> void:")
	var j := src.find("func _draw_light_cone(")
	return src.substr(i, j - i) if i >= 0 and j > i else ""


func _initialize() -> void:
	src = FileAccess.get_file_as_string("res://scripts/arena.gd")
	_expect(src.length() > 30000, "arena.gd source readable")

	# ── 1. 贴图与覆盖矩形 ──────────────────────────────────
	_expect(_real_count("draw_texture_rect(BackdropTexture, Rect2(-40, -40, 1360, 800), false)") == 1,
		"opaque backdrop draw form present exactly once")
	_expect(_real_count("draw_rect(Rect2(-40, -40, 1360, 800), Color(0.055, 0.045, 0.085, 0.20))") == 1,
		"backdrop dim overlay present exactly once")
	var img: Image = Backdrop.get_image()
	_expect(img != null, "backdrop image readable")
	if img != null:
		_expect(img.detect_alpha() == Image.ALPHA_NONE, "backdrop has no alpha channel")
		_expect(img.get_width() > 0 and img.get_height() > 0, "backdrop non-empty")
	# Rect2(-40,-40,1360,800) ⊇ 视口 [0,1280]x[0,720]
	_expect(-40.0 <= 0.0 and -40.0 + 1360.0 >= 1280.0
		and -40.0 <= 0.0 and -40.0 + 800.0 >= 720.0,
		"texture rect covers whole viewport")

	# ── 2. 被覆盖的死绘制已退役（逐形态 0 处真实代码行）──────
	var dead := [
		"func _build_backdrop()", "_build_backdrop()", "_background_cache",
		"var bands := [", "lamp_color", "rng.randf_range",
		"sin(_time * 1.7", "for rect: Rect2 in", '"lamps"',
		"Color(0.035, 0.045, 0.085)", "GROUND_Y + 12.0 - h",
	]
	for form: String in dead:
		_expect(_real_count(form) == 0, "dead form retired: " + form)

	# ── 3. 仍要画的动态玩法层保留 ────────────────────────────
	_expect(_real_count("func _draw_backdrop() -> void:") == 1, "backdrop function present")
	_expect(_real_count("\t_draw_backdrop()") == 1, "backdrop called once from _draw")
	_expect(_real_count("_draw_light_cone(") >= 3, "light cones kept (def + 2 calls)")
	_expect(_real_count("_draw_floor_glow(") >= 3, "floor glows kept (def + 2 calls)")
	# range(9) 在别处也有循环，全文件数 ==1 会误报；只钉背景函数体内。
	var body := _backdrop_body()
	_expect(body != "", "backdrop body slice found")
	_expect(body.count("for i in range(9)") == 1, "9 horizontal floor lines kept in backdrop")
	_expect(body.count("range(13)") == 1, "13 perspective floor lines kept in backdrop")
	_expect(body.count("draw_line(") >= 2, "floor lines actually drawn")
	_expect(_real_count("draw_set_transform(offset)") == 1, "shake transform kept")
	_expect(_real_count("func _shake_offset() -> Vector2:") == 1, "shake offset helper kept")

	# ── 4. 判定与已接线层零回归 ──────────────────────────────
	var kept_once := [
		'const BATTLE_MODE := "taikou"',
		"const TK_MAX_TURNS := 3",
		"const GROUND_Y := 520.0",
		'const Rhythm = preload("res://scripts/battle_rhythm.gd")',
		"_draw_rhythm_fx(canvas)",
		"MotionP0.binding_for(winner_type)",
		"func _apply_rhythm_visuals() -> void:",
		"tk_damage = Rules.damage_of(tk_player_result)",
	]
	for form: String in kept_once:
		_expect(_real_count(form) == 1, "kept exactly once: " + form)
	_expect(_real_count("_maybe_capture()") >= 2, "capture hooks kept")

	if _failures.is_empty():
		print("ENGINE OPT CHECK: %d/%d passed" % [_total, _total])
		quit(0)
	else:
		for line: String in _failures:
			print("FAIL: ", line)
		print("ENGINE OPT CHECK: %d/%d failed" % [_failures.size(), _total])
		quit(1)
