extends SceneTree
## 静止帧redraw-on-demand A/B（真实 GL 窗口，不能 --headless）。
##
## 跑法：
##   CARD_BOXER_REDRAW_OUT=<dir> godot --path . --resolution 1280x720 \
##     --quit-after 2000 --script res://tests/redraw_probe.gd
##
## 关键设计：**同一进程、同一棵注入态的树**，只切 arena.redraw_gate_enabled。
## 这样绕开上一轮踩过的坑（Godot 每次启动随机化全局 RNG，跨运行手牌不同，
## 逐像素 identical 判据会假红）。注入态把 hand / hp / tk_* / rage / banner
## 全部写死，fighters 在 paused 下不 tick，呼吸也停，画面每帧确定。
##
## 五张 PNG 的用途：
##   A 关闭 / B 开启          → 静止帧像素等价
##   C 变更开启 / D 变更关闭  → 状态变化后仍然像素等价（证明没有停更）
##   E 回退开启 / A 关闭      → 改回去也能刷新，不残留旧帧

const ArenaScene = preload("res://scenes/main.tscn")

const HAND_A := ["jab", "cross", "guard", "wave", "uppercut"]
const HAND_B := ["throw", "cross", "guard", "wave", "uppercut"]

# name / gate / state / frames / warmup / png
const PHASES := [
	{"name": "off", "gate": false, "state": "a", "frames": 90, "warmup": 25,
		"png": "A_still-disabled.png"},
	{"name": "on", "gate": true, "state": "a", "frames": 90, "warmup": 25,
		"png": "B_still-enabled.png"},
	{"name": "changed_on", "gate": true, "state": "b", "frames": 70, "warmup": 20,
		"png": "C_modified-enabled.png"},
	{"name": "changed_off", "gate": false, "state": "b", "frames": 70, "warmup": 20,
		"png": "D_modified-disabled.png"},
	{"name": "back_on", "gate": true, "state": "a", "frames": 70, "warmup": 20,
		"png": "E_rollback-enabled.png"},
]


class Driver:
	extends Node

	var arena: Node2D
	var out_dir := ""
	var phases: Array = []
	var hand_a: Array = []
	var hand_b: Array = []
	var n := 0
	var busy := false
	var phase := 0
	var phase_frames := 0
	var proc_ms: Array = []
	var records: Array = []
	var start_stats: Dictionary = {}

	func _mean(v: Array) -> float:
		var s := 0.0
		for x in v:
			s += float(x)
		return s / float(v.size()) if v.size() > 0 else 0.0

	func _median(v: Array) -> float:
		var a := v.duplicate()
		a.sort()
		return float(a[int(a.size() / 2)]) if a.size() > 0 else 0.0

	func _delta() -> Dictionary:
		var d := {}
		for k in arena.redraw_stats.keys():
			d[k] = int(arena.redraw_stats[k]) - int(start_stats.get(k, 0))
		return d

	func _inject(state: String) -> void:
		var a = arena
		a.hand = (hand_a if state == "a" else hand_b).duplicate()
		a.cooldowns = [0.0, 0.0, 0.0, 0.0, 0.0]
		a.tk_phase = "select"
		a.tk_marks = []
		a.tk_player_reveal = []
		a.tk_enemy_reveal = []
		a.tk_player_result = {}
		a.tk_enemy_result = {}
		a.tk_winner = ""
		a.tk_motion_id = ""
		a.tk_motion_label = ""
		a.tk_react_id = ""
		a.tk_player_ex = false
		a.tk_enemy_ex = false
		a.tk_player_ex_boosted = false
		a.tk_enemy_ex_boosted = false
		a.tk_player_rage = 0.0
		a.tk_enemy_rage = 0.0
		a.tk_rhythm_t = -1.0
		a.tk_rhythm_winner = ""
		a.tk_rhythm_hit = false
		a.effects = []
		a.projectiles = []
		a._shake = 0.0
		a._flash = 0.0
		a._global_hitstop = 0.0
		a.banner_time = 0.0
		a.banner_text = ""
		a.banner_sub = ""
		a.selected_index = -1
		a.combo_shown = 0.0
		a.combo_count = 0
		a.player.hp = 100
		a.enemy.hp = 100
		a.player.meter = 0.0
		a.enemy.meter = 0.0
		a.player.visual_shift = Vector2.ZERO
		a.enemy.visual_shift = Vector2.ZERO
		a.player.visual_tilt = 0.0
		a.enemy.visual_tilt = 0.0
		a.hud._hp_shown = {"p": 1.0, "e": 1.0}

	func _apply(cfg: Dictionary) -> void:
		arena.redraw_gate_enabled = bool(cfg["gate"])
		_inject(String(cfg["state"]))
		start_stats = arena.redraw_stats.duplicate()

	func _setup() -> void:
		if arena.player == null:
			print("REDRAW_PROBE_FAILED arena not ready")
			get_tree().quit(1)
			return
		arena.paused = true
		_apply(phases[0])

	func _finish() -> void:
		var payload := {
			"phases": records,
			"viewport": [1280, 720],
			"gate_default": true,
			"source": "tests/redraw_probe.gd",
		}
		var f := FileAccess.open(out_dir + "/probe_result.json", FileAccess.WRITE)
		if f != null:
			f.store_string(JSON.stringify(payload, "\t"))
			f.close()
		print("REDRAW_PROBE_DONE phases=%d" % records.size())
		get_tree().quit(0)

	func _process(_delta: float) -> void:
		if busy:
			return
		busy = true
		n += 1
		if n == 1:
			_setup()
		var cfg: Dictionary = phases[phase]
		phase_frames += 1
		if phase_frames > int(cfg["warmup"]):
			proc_ms.append(Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0)
		if phase_frames >= int(cfg["frames"]):
			await RenderingServer.frame_post_draw
			var image := get_viewport().get_texture().get_image()
			var path := out_dir + "/" + String(cfg["png"])
			image.save_png(path)
			records.append({
				"name": String(cfg["name"]),
				"gate": bool(cfg["gate"]),
				"state": String(cfg["state"]),
				"png": String(cfg["png"]),
				"frames": phase_frames,
				"sampled": proc_ms.size(),
				"process_ms": {"mean": _mean(proc_ms), "median": _median(proc_ms)},
				"raw_process_ms": proc_ms.duplicate(),
				"redraw_delta": _delta(),
			})
			phase += 1
			phase_frames = 0
			proc_ms = []
			if phase >= phases.size():
				_finish()
				return
			_apply(phases[phase])
		busy = false


func _initialize() -> void:
	var out_dir := OS.get_environment("CARD_BOXER_REDRAW_OUT")
	if out_dir == "":
		print("缺少 CARD_BOXER_REDRAW_OUT")
		quit(1)
		return
	var a: Node2D = ArenaScene.instantiate()
	root.add_child(a)
	var d := Driver.new()
	d.arena = a
	d.out_dir = out_dir
	d.phases = PHASES.duplicate(true)
	d.hand_a = HAND_A.duplicate()
	d.hand_b = HAND_B.duplicate()
	root.add_child(d)
	print("REDRAW_PROBE_START phases=%d" % PHASES.size())
