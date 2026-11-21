extends SceneTree
## 引擎内帧开销 + 同状态像素基线探针（真实 GL 窗口，不能 --headless）。
##
## 跑法：
##   CARD_BOXER_PERF_OUT=<png> CARD_BOXER_PERF_JSON=<json> \
##     godot --path . --quit-after 900 --script res://tests/perf_probe.gd
##
## 冻结手法：实例化 main.tscn 后立刻 paused=true，并隐藏所有动态子节点。
## arena._process 只走 paused 分支（queue_redraw + return），_shake 恒为 0，
## _shake_offset() 恒为 Vector2.ZERO —— 于是每帧像素完全确定，可用于
## 优化前/后的逐像素等价证明；同时 Performance 照常统计每帧绘制命令数。

const ArenaScene = preload("res://scenes/main.tscn")


class Driver:
	extends Node
	var arena: Node2D
	var out_png := ""
	var out_json := ""
	var samples := 120
	var warmup := 20
	var n := 0
	var busy := false
	var proc_ms: Array = []
	var prims: Array = []
	var calls: Array = []

	func _median(v: Array) -> float:
		var a := v.duplicate()
		a.sort()
		return float(a[int(a.size() / 2)])

	func _mean(v: Array) -> float:
		var s := 0.0
		for x in v:
			s += float(x)
		return s / float(v.size())

	func _p95(v: Array) -> float:
		var a := v.duplicate()
		a.sort()
		return float(a[mini(a.size() - 1, int(float(a.size()) * 0.95))])

	func _process(_delta: float) -> void:
		if busy:
			return
		busy = true
		n += 1

		if n == 1:
			arena.paused = true
			for c in arena.get_children():
				c.visible = false

		if n > warmup and n <= warmup + samples:
			proc_ms.append(Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0)
			prims.append(Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME))
			calls.append(Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME))

		if n == warmup + samples + 1:
			await RenderingServer.frame_post_draw
			var image := get_viewport().get_texture().get_image()
			image.save_png(out_png)
			var payload := {
				"viewport": [image.get_width(), image.get_height()],
				"warmup": warmup,
				"samples": proc_ms.size(),
				"process_ms": {"mean": _mean(proc_ms), "median": _median(proc_ms), "p95": _p95(proc_ms)},
				"primitives": {"mean": _mean(prims), "min": prims.min(), "max": prims.max()},
				"draw_calls": {"mean": _mean(calls), "min": calls.min(), "max": calls.max()},
				"raw_process_ms": proc_ms,
				"raw_primitives": prims,
				"raw_draw_calls": calls,
			}
			var f := FileAccess.open(out_json, FileAccess.WRITE)
			if f != null:
				f.store_string(JSON.stringify(payload, "\t"))
				f.close()
			print("PERF_PROBE_DONE out=%s json=%s prims_mean=%.2f calls_mean=%.2f proc_ms=%.5f"
				% [out_png, out_json, _mean(prims), _mean(calls), _mean(proc_ms)])
			get_tree().quit(0)
			return
		busy = false


func _init() -> void:
	var out_png := OS.get_environment("CARD_BOXER_PERF_OUT")
	var out_json := OS.get_environment("CARD_BOXER_PERF_JSON")
	if out_png == "" or out_json == "":
		print("缺少 CARD_BOXER_PERF_OUT / CARD_BOXER_PERF_JSON")
		quit(1)
		return
	var a: Node2D = ArenaScene.instantiate()
	root.add_child(a)
	var d := Driver.new()
	d.arena = a
	d.out_png = out_png
	d.out_json = out_json
	var frames := OS.get_environment("CARD_BOXER_PERF_FRAMES")
	if frames != "":
		d.samples = int(frames)
	root.add_child(d)
	print("PERF_PROBE_START samples=%d" % d.samples)
