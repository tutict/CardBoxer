extends SceneTree

const ArenaScript = preload("res://scripts/arena.gd")
var checks := 0
var failures: Array[String] = []

func _initialize() -> void:
	call_deferred("run_checks")

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures.append(label)

func run_checks() -> void:
	for mode in ["tactical", "taikou", "realtime"]:
		for old_switch in ["", "0"]:
			OS.set_environment("CARD_BOXER_BATTLE_MODE", mode)
			OS.set_environment("CARD_BOXER_3D", old_switch)
			var arena = ArenaScript.new()
			root.add_child(arena)
			await process_frame
			var label := "%s with legacy switch '%s'" % [mode, old_switch]
			expect(arena.use_3d, "native rendering starts: " + label)
			expect(arena.layer_3d != null, "player model loads: " + label)
			expect(arena.layer_3d_foe != null, "opponent model loads: " + label)
			expect(arena.native_library != null, "native animation library loads: " + label)
			arena.queue_free()
			await process_frame
	for failure in failures:
		print("FAIL: ", failure)
	print("NATIVE STARTUP CHECK: %d/%d passed" % [checks - failures.size(), checks])
	quit(0 if failures.is_empty() else 1)
