extends SceneTree
## 按需重绘承重自检（源码形态 + 运行态键行为）。
##
## 跑法：godot --headless --path . --script res://tests/redraw_gate_check.gd
## 退出码 0 = 全过，1 = 有断言失败。
##
## 最硬的一条是「hud.gd 里出现的每个 arena.<field> 都必须在 _visual_key()
## 的快照里」——漏列一个字段就意味着那一层可能停更在旧画面。

const ArenaScene = preload("res://scenes/main.tscn")

var _failures: Array = []
var _total := 0
var arena_src := ""
var hud_src := ""
var fx_src := ""
var fighter_src := ""


func _expect(cond: bool, label: String) -> void:
	_total += 1
	if not cond:
		_failures.append(label)


## 只数真实代码行：排除整行注释与行内注释之后的形态。
func _real(src: String, form: String) -> int:
	var n := 0
	for ln in src.split("\n"):
		var s := ln.strip_edges()
		if s.begins_with("#"):
			continue
		var i := ln.find(form)
		if i < 0:
			continue
		if ln.substr(0, i).find("#") >= 0:
			continue
		n += 1
	return n


func _slice(src: String, begin: String, end: String) -> String:
	var i := src.find(begin)
	var j := src.find(end)
	return src.substr(i, j - i) if i >= 0 and j > i else ""


func _initialize() -> void:
	call_deferred("_run_checks")

func _run_checks() -> void:
	arena_src = FileAccess.get_file_as_string("res://scripts/arena.gd")
	hud_src = FileAccess.get_file_as_string("res://scripts/hud.gd")
	fx_src = FileAccess.get_file_as_string("res://scripts/fx_layer.gd")
	fighter_src = FileAccess.get_file_as_string("res://scripts/fighter.gd")
	_expect(arena_src.length() > 40000 and hud_src.length() > 20000,
		"arena.gd / hud.gd source readable")

	var proc := _slice(arena_src, "func _process(delta: float) -> void:",
		"func _capture_hit_shot()")
	_expect(proc.length() > 500, "_process slice found")
	_expect(_real(proc, "_request_redraw()") == 3,
		"three branches all go through _request_redraw()")
	_expect(_real(proc, "fx_layer.queue_redraw()") == 0
		and _real(proc, "\t\tqueue_redraw()") == 0
		and _real(proc, "\tqueue_redraw()") == 0,
		"no unconditional queue_redraw left in _process")
	_expect(_real(proc, "_maybe_capture()") == 2,
		"capture chain survives: hitstop + main branch")

	var key_body := _slice(arena_src, "func _arena_visual_key() -> String:",
		"func _request_redraw()")
	for token in ["_shake > 0.05", "_flash", "player.position.x",
			"enemy.position.x", "world.position", "fx_layer.position",
			"effects", "projectiles", "tk_rhythm_t", "tk_rhythm_winner",
			"tk_rhythm_hit", "visual_shift"]:
		_expect(key_body.find(token) >= 0, "arena key covers: " + token)

	var hud_key := _slice(hud_src, "func _visual_key() -> String:",
		"func _process(delta: float) -> void:")
	_expect(hud_key.find("_time if pulsing else -1.0") >= 0,
		"pulse clock only enters key when a pulse is actually running")
	_expect(_real(hud_src, "var _last_visual_key := \"\"") == 1,
		"empty-string sentinel guarantees first-frame draw")
	_expect(_real(arena_src, "var _force_redraw := true") == 1,
		"first frame force flag present")
	_expect(_real(arena_src, "var redraw_gate_enabled := true") == 1,
		"gate enabled by default")

	# HUD 快照完整性：hud.gd 里每一个 arena.<field> 都要在快照里。
	var re := RegEx.new()
	re.compile("arena\\.([A-Za-z_][A-Za-z0-9_]*)")
	var seen: Dictionary = {}
	for m in re.search_all(hud_src):
		seen[m.get_string(1)] = true
	var plumbing := ["redraw_gate_enabled", "redraw_stats"]
	for field in seen.keys():
		if plumbing.has(field):
			continue
		_expect(hud_key.find("a.%s" % field) >= 0,
			"hud key covers arena." + String(field))

	_expect(_real(fx_src, "fx_draws") >= 1, "fx_layer draw counter wired")
	_expect(_real(hud_src, "hud_draws") >= 1, "hud draw counter wired")
	_expect(_real(arena_src, "arena_draws") >= 1, "arena draw counter wired")
	_expect(fighter_src.find("redraw_stats") < 0
		and fighter_src.find("_visual_key") < 0,
		"fighter.gd deliberately left on per-frame redraw")

	# ── 运行态 ────────────────────────────────────────────────
	var a: Node2D = ArenaScene.instantiate()
	root.add_child(a)
	# SceneTree._initialize() 阶段主循环未起，add_child 不触发 _ready()。
	if a.player == null:
		a._ready()
	var h = a.hud
	_expect(bool(a.redraw_gate_enabled), "runtime: gate on by default")
	_expect(bool(a._force_redraw), "runtime: first frame forced")
	var k0: String = a._arena_visual_key()
	_expect(k0 == a._arena_visual_key(), "runtime: arena key stable at rest")
	a.effects.append({"t": 0.1})
	_expect(a._arena_visual_key() != k0, "runtime: effects change arena key")
	a.effects.clear()
	a._shake = 9.0
	_expect(String(a._arena_visual_key()).begins_with("shake:"),
		"runtime: shake forces per-frame redraw")
	a._shake = 0.0

	var hk0: String = h._visual_key()
	_expect(hk0 == h._visual_key(), "runtime: hud key stable at rest")
	h._time += 0.05
	_expect(h._visual_key() == hk0, "runtime: idle clock does NOT dirty hud")
	h._time -= 0.05
	var old_hand: Array = a.hand.duplicate()
	# 初始手牌由 arena.gd 的 randi 洗牌发出，原先硬写 "wave" 会在 hand[0]
	# 恰好已经是 "wave" 时假红（原版实测 1/30、接线版 2/30，见 probe_flaky.json）。
	# 改成「一定与原值不同」的值，让这条承重断言确定性成立。
	a.hand[0] = "wave" if String(a.hand[0]) != "wave" else "jab"
	_expect(h._visual_key() != hk0, "runtime: hand change dirties hud")
	a.hand = old_hand
	var hk1: String = h._visual_key()
	a.tk_phase = "resolve"
	_expect(h._visual_key() != hk1, "runtime: phase change dirties hud")

	a.player.hp = 1
	var hp_key: String = h._visual_key()
	h._time += 0.05
	_expect(h._visual_key() != hp_key, "runtime: low-hp pulse clock dirties hud")
	h._time -= 0.05

	a.redraw_stats["arena_queued"] = 0
	a.redraw_stats["arena_skipped"] = 0
	a._force_redraw = false
	a._last_arena_key = a._arena_visual_key()
	a._request_redraw()
	_expect(int(a.redraw_stats["arena_skipped"]) == 1,
		"runtime: unchanged key is skipped")
	a.force_redraw()
	a._request_redraw()
	_expect(int(a.redraw_stats["arena_queued"]) == 1,
		"runtime: force_redraw() queues")
	a.redraw_gate_enabled = false
	a._request_redraw()
	_expect(int(a.redraw_stats["arena_queued"]) == 2,
		"runtime: gate off always queues")

	var passed: int = _total - _failures.size()
	print("REDRAW GATE CHECK: %d/%d passed" % [passed, _total])
	for f in _failures:
		print("FAIL: " + String(f))
	quit(0 if _failures.is_empty() else 1)
