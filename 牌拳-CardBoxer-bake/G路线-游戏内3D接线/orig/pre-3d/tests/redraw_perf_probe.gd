extends SceneTree
## 按需重绘的帧开销探针（真实 GL 窗口，每次运行只测一种 gate 模式）。
##
## 与 引擎优化/perf_probe.gd 同口径：main.tscn -> paused=true -> 隐藏动态
## 子节点 -> 120 帧 Performance 采样 -> 冻结态纯背景 PNG。
## 两种 gate 模式分两次进程跑，避免「同一进程里存 PNG 之后 TIME_PROCESS
## 被窗口节流冻结」的污染（见 按需重绘/对比帧/ 五段探针的负结果）。
##
## 跑法：
##   CARD_BOXER_REDRAW_GATE=0|1 CARD_BOXER_REDRAW_PERF_OUT=<png> \
##   CARD_BOXER_REDRAW_PERF_JSON=<json> \
##     godot --path . --resolution 1280x720 --quit-after 900 \
##       --script res://tests/redraw_perf_probe.gd

const ArenaScene = preload("res://scenes/main.tscn")


class Driver:
	extends Node
	var arena: Node2D
	var out_png := ""
	var out_json := ""
	var gate := true
	var samples := 120
	var warmup := 20
	var n := 0
	var busy := false
	var proc_ms: Array = []
	var prims: Array = []
	var calls: Array = []

	func _mean(v: Array) -> float:
		var s := 0.0
		for x in v:
			s += float(x)
		return s / float(v.size())

	func _median(v: Array) -> float:
		var a := v.duplicate()
		a.sort()
		return float(a[int(a.size() / 2)])

	func _process(_delta: float) -> void:
		if busy:
			return
		busy = true
		n += 1
		if n == 1:
			arena.paused = true
			arena.redraw_gate_enabled = gate
			for c in arena.get_children():
				c.visible = false
		# 采样窗口开始处清零：只统计这 120 帧，排除首帧字体/贴图预热。
		if n == warmup + 1:
			for k in arena.redraw_stats.keys():
				arena.redraw_stats[k] = 0
		if n > warmup and n <= warmup + samples:
			proc_ms.append(Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0)
			prims.append(Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME))
			calls.append(Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME))
		if n == warmup + samples + 1:
			await RenderingServer.frame_post_draw
			var image := get_viewport().get_texture().get_image()
			image.save_png(out_png)
			var payload := {
				"gate": gate,
				"viewport": [image.get_width(), image.get_height()],
				"samples": proc_ms.size(),
				"redraw_stats": arena.redraw_stats.duplicate(),
				"process_ms": {"mean": _mean(proc_ms), "median": _median(proc_ms)},
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
			print("REDRAW_PERF_DONE gate=%s prims=%.2f calls=%.2f proc_ms=%.5f draws=%d skipped=%d"
				% [str(gate), _mean(prims), _mean(calls), _mean(proc_ms),
					int(arena.redraw_stats["arena_draws"]),
					int(arena.redraw_stats["arena_skipped"])])
			get_tree().quit(0)
			return
		busy = false


func _initialize() -> void:
	var out_png := OS.get_environment("CARD_BOXER_REDRAW_PERF_OUT")
	var out_json := OS.get_environment("CARD_BOXER_REDRAW_PERF_JSON")
	if out_png == "" or out_json == "":
		print("缺少 CARD_BOXER_REDRAW_PERF_OUT / CARD_BOXER_REDRAW_PERF_JSON")
		quit(1)
		return
	var a: Node2D = ArenaScene.instantiate()
	root.add_child(a)
	var d := Driver.new()
	d.arena = a
	d.out_png = out_png
	d.out_json = out_json
	d.gate = OS.get_environment("CARD_BOXER_REDRAW_GATE") != "0"
	root.add_child(d)
	print("REDRAW_PERF_START gate=%s" % str(d.gate))
