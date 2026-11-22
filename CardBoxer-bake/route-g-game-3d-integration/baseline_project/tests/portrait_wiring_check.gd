extends SceneTree
## 静态 UI 位接入的承重守卫（引擎侧，四组独立断言）。
##
## 跑法：godot --headless --path . --script res://tests/portrait_wiring_check.gd
##
## 1) 贴图真空：8 张 PNG 真的在 res://、sha256 与 manifest 一致、
##    能 load 成 Texture2D、尺寸/alpha/覆盖率达标、.ctex 非空。
## 2) 接线形态：只给第 1/5 张加插画、中间三张调用形态不变、
##    rank/牌名/描述/冷却绘制仍在、头像与档案板画在正确位置。
## 3) _visual_key()：补了新 token、静止时钟不脏、切页/切开关必脏；
##    并按 redraw_gate_check.gd 同口径复算 arena.<field> 全量覆盖。
## 4) 零污染：fighter.gd / arena.gd / project.godot 维持既有形态，
##    且既有抖动手牌断言保持确定性。

const HUD_SRC := "res://scripts/hud.gd"
const FIGHTER_SRC := "res://scripts/fighter.gd"
const ARENA_SRC := "res://scripts/arena.gd"
const GATE_SRC := "res://tests/redraw_gate_check.gd"
const PROJ_SRC := "res://project.godot"
const MANIFEST := "res://assets/portraits/manifest.json"
const DIR := "res://assets/portraits/"
const ArenaScene = preload("res://scenes/main.tscn")

var _total := 0
var _failures: Array[String] = []


func _expect(cond: bool, label: String) -> void:
	_total += 1
	if not cond:
		_failures.append(label)


func _read(path: String) -> String:
	return FileAccess.get_file_as_string(path)


func _slice(src: String, from: String, to: String) -> String:
	var i := src.find(from)
	if i < 0:
		return ""
	var j := src.find(to, i + from.length())
	if j < 0:
		return ""
	return src.substr(i, j - i)


func _sha256(path: String) -> String:
	var bytes := FileAccess.get_file_as_bytes(path)
	if bytes.is_empty():
		return ""
	var ctx := HashingContext.new()
	ctx.start(HashingContext.HASH_SHA256)
	ctx.update(bytes)
	return ctx.finish().hex_encode()


func _coverage(img: Image) -> float:
	var data := img.get_data()
	var hit := 0
	for i in range(0, data.size(), 4):
		if data[i + 3] > 8:
			hit += 1
	return float(hit) / float(data.size() / 4)


# ── 1) 贴图真空 ────────────────────────────────────────────────

func _check_assets() -> void:
	var txt := _read(MANIFEST)
	_expect(not txt.is_empty(), "manifest readable")
	var parsed: Variant = JSON.parse_string(txt)
	_expect(parsed is Dictionary, "manifest parses as dictionary")
	if not (parsed is Dictionary):
		return
	var files: Dictionary = (parsed as Dictionary).get("files", {})
	_expect(files.size() == 8, "manifest lists 8 pngs")
	for name: Variant in files.keys():
		var fname := String(name)
		var png := DIR + fname
		var meta: Dictionary = files[name]
		_expect(FileAccess.file_exists(png), "png exists: " + fname)
		_expect(_sha256(png) == String(meta["sha256"]), "png sha256 matches: " + fname)
		var tex: Variant = load(png)
		_expect(tex is Texture2D, "texture loads: " + fname)
		# 即使 load 失败也继续查 .import / .ctex，才能定位「贴图真空」的根因，
		# 而不是一句 load 失败就跳过后面所有证据。
		if tex is Texture2D:
			var t: Texture2D = tex
			var want: Array = meta["size"]
			_expect(t.get_width() == int(want[0]) and t.get_height() == int(want[1]),
				"texture size: " + fname)
			var img := t.get_image()
			_expect(img != null, "texture image: " + fname)
			if img != null:
				_expect(img.detect_alpha() != Image.ALPHA_NONE, "has alpha: " + fname)
				_expect(_coverage(img) > 0.05, "texture not blank: " + fname)
				_expect(img.get_pixel(0, 0).a < 0.02, "corner transparent: " + fname)

		# .import 指向的 .ctex 必须真的存在且非空，防「只有 .import 没有资源」。
		var imp := _read(png + ".import")
		_expect(imp.contains('source_file="res://assets/portraits/' + fname + '"'),
			"import source_file: " + fname)
		var re := RegEx.new()
		re.compile('path="(res://[^"]+)"')
		var m := re.search(imp)
		_expect(m != null, "import has ctex path: " + fname)
		if m != null:
			var ctex := m.get_string(1)
			_expect(FileAccess.file_exists(ctex) and not FileAccess.get_file_as_bytes(ctex).is_empty(),
				"ctex exists and nonempty: " + fname)


# ── 2) 接线形态 ────────────────────────────────────────────────

func _check_wiring() -> void:
	var src := _read(HUD_SRC)
	_expect(src.count("const TEX_") == 8, "8 texture preloads")
	_expect(src.count("draw_texture_rect(") >= 5, "texture draw calls present")
	_expect(src.contains("if portrait_ui_enabled and (i == 0 or i == 4):"),
		"only card 1/5 get portrait background")
	_expect(src.count("_draw_card(Vector2(x, HAND_Y), String(id), i, arena.cooldowns[i])") == 1,
		"middle three cards keep original call shape")
	var card := _slice(src, "func _draw_card(", "func _draw_empty_slot(")
	for token in ["String(card[\"name\"])", "rank_text", "card[\"text\"]",
			"cooldown > 0.0", "_wrap("]:
		_expect(card.contains(token), "card info preserved: " + token)
	_expect(_slice(src, "func _draw_hud_bars(", "func _draw_bar(").contains("_draw_avatars()"),
		"avatars drawn with hud bars")
	_expect(_slice(src, "func _draw() -> void:", "func _draw_hud_bars(").contains("_draw_profile()"),
		"profile drawn last in _draw()")
	_expect(src.contains("KEY_TAB"), "TAB edge polling present")


# ── 3) _visual_key() + 运行态 ─────────────────────────────────

func _check_visual_key() -> void:
	var src := _read(HUD_SRC)
	var key := _slice(src, "func _visual_key() -> String:", "func _poll_profile_tab()")
	_expect(not key.is_empty(), "visual_key slice found")
	_expect(key.contains("_profile_page"), "visual key covers _profile_page")
	_expect(key.contains("portrait_ui_enabled"), "visual key covers portrait_ui_enabled")
	var re := RegEx.new()
	re.compile("arena\\.([A-Za-z_][A-Za-z0-9_]*)")
	var seen: Dictionary = {}
	for m in re.search_all(src):
		seen[m.get_string(1)] = true
	for field: Variant in seen.keys():
		if field == "redraw_gate_enabled" or field == "redraw_stats":
			continue
		_expect(key.contains("a." + String(field)), "hud key covers arena." + String(field))

	var a: Node2D = ArenaScene.instantiate()
	root.add_child(a)
	if a.player == null:
		a._ready()
	var h = a.hud
	var k0: String = h._visual_key()
	_expect(k0 == h._visual_key(), "hud key stable at rest")
	h._time += 0.05
	_expect(h._visual_key() == k0, "idle clock does NOT dirty hud")
	h._time -= 0.05
	h._profile_page = 1
	_expect(h._visual_key() != k0, "profile page dirties hud")
	h._profile_page = 0
	h.portrait_ui_enabled = false
	_expect(h._visual_key() != k0, "portrait switch dirties hud")
	h.portrait_ui_enabled = true
	_expect(h._visual_key() == k0, "restored visual key equals baseline")

	# 边沿逻辑逐条验（不伪造 OS 按键）；源码另断言它确实接在真实 KEY_TAB 上。
	_expect(src.contains("Input.is_key_pressed(KEY_TAB)"), "TAB polling wired to real input")
	h._profile_tab_edge(true)
	_expect(h._profile_page == 1, "TAB down advances profile page once")
	h._profile_tab_edge(true)
	_expect(h._profile_page == 1, "holding TAB does not repeat")
	h._profile_tab_edge(false)
	_expect(not h._profile_tab_held, "TAB release clears latch")
	h._profile_tab_edge(true)
	_expect(h._profile_page == 2, "second TAB press advances to page 2")
	h._profile_tab_edge(false)
	h._profile_page = 0


# ── 4) 零污染 ─────────────────────────────────────────────────

func _check_no_pollution() -> void:
	var fighter := _read(FIGHTER_SRC)
	_expect(not fighter.contains("TEX_"), "fighter.gd has no portrait preloads")
	_expect(not fighter.contains("portrait_ui_enabled"), "fighter.gd has no portrait switch")
	_expect(fighter.find("redraw_stats") < 0, "fighter.gd still per-frame redraw")
	var arena_src := _read(ARENA_SRC)
	_expect(arena_src.count("draw_texture_rect(BackdropTexture, Rect2(-40, -40, 1360, 800), false)") == 1,
		"arena.gd keeps exactly one backdrop draw")
	_expect(not arena_src.contains("TEX_CARD"), "arena.gd has no portrait draws")
	_expect(_read(PROJ_SRC).contains('window/stretch/mode="canvas_items"'),
		"project.godot stretch unchanged")
	_expect(_read(GATE_SRC).contains('a.hand[0] = "wave" if String(a.hand[0]) != "wave" else "jab"'),
		"flaky hand-change assertion stays deterministic")


func _initialize() -> void:
	_check_assets()
	_check_wiring()
	_check_visual_key()
	_check_no_pollution()
	if _failures.is_empty():
		print("PORTRAIT WIRING CHECK: %d/%d passed" % [_total, _total])
		quit(0)
	else:
		for f in _failures:
			print("FAIL: ", f)
		print("PORTRAIT WIRING CHECK: %d failed" % _failures.size())
		quit(1)
