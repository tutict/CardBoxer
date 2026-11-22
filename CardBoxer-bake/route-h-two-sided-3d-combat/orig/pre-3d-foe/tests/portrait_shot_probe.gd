extends SceneTree
## 静态 UI 位接入的引擎内实渲取证（真实 GL 窗口，不能 --headless）。
##
## 跑法：
##   CARD_BOXER_PORTRAIT_OUT=<dir> godot --path . --resolution 1280x720 \
##     --quit-after 2000 --script res://tests/portrait_shot_probe.gd
##
## 同一进程、同一棵注入态的树，只切 hud.portrait_ui_enabled / hud._profile_page。
## 这样跨相位比较绕开 Godot 每次启动随机化全局 RNG 的坑（见 redraw_probe.gd）。
## 五相：A 接线前基线 / B 接线后关板 / C 档案页1 / D 档案页2 / E 回退关板。

const ArenaScene = preload("res://scenes/main.tscn")
const HAND_A := ["jab", "cross", "guard", "wave", "uppercut"]

## A~E 冻结模拟（paused=true）做确定性逐像素证据；F 不暂停，只作交付展示，
## 让画面不盖「暂停」二字。F 不参与任何 A/B 判据。
const PHASES := [
	{"name": "baseline", "portrait": false, "page": 0, "paused": true,
		"frames": 60, "warmup": 15, "png": "A_baseline-without-portraits.png"},
	{"name": "wired", "portrait": true, "page": 0, "paused": true,
		"frames": 60, "warmup": 15, "png": "B_integration-panel-closed.png"},
	{"name": "page1", "portrait": true, "page": 1, "paused": true,
		"frames": 60, "warmup": 15, "png": "C_profile-page-1.png"},
	{"name": "page2", "portrait": true, "page": 2, "paused": true,
		"frames": 60, "warmup": 15, "png": "D_profile-page-2.png"},
	{"name": "back", "portrait": true, "page": 0, "paused": true,
		"frames": 60, "warmup": 15, "png": "E_rollback-panel-closed.png"},
	{"name": "clean", "portrait": true, "page": 0, "paused": false,
		"frames": 90, "warmup": 15, "png": "F_live-unpaused.png"},
]


class Driver:
	extends Node

	var arena: Node2D
	var out_dir := ""
	var phases: Array = []
	var n := 0
	var busy := false
	var phase := 0
	var phase_frames := 0
	var records: Array = []

	func _inject() -> void:
		var a = arena
		a.hand = HAND_A.duplicate()
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
		_inject()
		arena.paused = bool(cfg["paused"])
		arena.hud.portrait_ui_enabled = bool(cfg["portrait"])
		arena.hud._profile_page = int(cfg["page"])
		arena.hud._last_visual_key = ""
		arena.force_redraw()

	func _setup() -> void:
		if arena.player == null:
			print("PORTRAIT_SHOT_PROBE_FAILED arena not ready")
			get_tree().quit(1)
			return
		arena.paused = true
		_apply(phases[0])

	func _finish() -> void:
		var payload := {
			"phases": records,
			"viewport": [1280, 720],
			"source": "tests/portrait_shot_probe.gd",
			"note": "same-process injected state; A/B via hud.portrait_ui_enabled",
		}
		var f := FileAccess.open(out_dir + "/probe_result.json", FileAccess.WRITE)
		if f != null:
			f.store_string(JSON.stringify(payload, "\t"))
			f.close()
		print("PORTRAIT_SHOT_PROBE_DONE phases=%d" % records.size())
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
		if phase_frames >= int(cfg["frames"]):
			await RenderingServer.frame_post_draw
			var image := get_viewport().get_texture().get_image()
			var path := out_dir + "/" + String(cfg["png"])
			image.save_png(path)
			records.append({
				"name": String(cfg["name"]),
				"portrait_ui_enabled": bool(cfg["portrait"]),
				"profile_page": int(cfg["page"]),
				"paused": bool(cfg["paused"]),
				"png": String(cfg["png"]),
				"frames": phase_frames,
				"image_size": [image.get_width(), image.get_height()],
			})
			phase += 1
			phase_frames = 0
			if phase >= phases.size():
				_finish()
				return
			_apply(phases[phase])
		busy = false


func _initialize() -> void:
	var out_dir := OS.get_environment("CARD_BOXER_PORTRAIT_OUT")
	if out_dir == "":
		print("缺少 CARD_BOXER_PORTRAIT_OUT")
		quit(1)
		return
	var a: Node2D = ArenaScene.instantiate()
	root.add_child(a)
	var d := Driver.new()
	d.arena = a
	d.out_dir = out_dir
	d.phases = PHASES.duplicate(true)
	root.add_child(d)
	print("PORTRAIT_SHOT_PROBE_START phases=%d" % PHASES.size())
