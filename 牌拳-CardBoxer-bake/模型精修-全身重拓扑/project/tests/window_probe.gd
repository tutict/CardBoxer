extends SceneTree
## 真实窗口下量物理窗口尺寸 / 逻辑画布尺寸 / 拉伸配置。
## 必须不带 --headless：dummy DisplayServer 没有真实窗口。
##
## 跑法：CARD_BOXER_WINDOW_JSON=<json> godot --path . --quit-after 120 \
##         --script res://tests/window_probe.gd
## 注意：不要传 --resolution，否则命令行会覆盖 project.godot 的窗口尺寸。


class Driver:
	extends Node
	var out_json := ""
	var n := 0

	func _process(_delta: float) -> void:
		n += 1
		if n < 3:
			return
		var phys: Vector2i = DisplayServer.window_get_size()
		var vp := get_viewport()
		var viewport_px: Vector2i = vp.size
		var visible: Rect2 = vp.get_visible_rect()
		var render_img := vp.get_texture().get_image()
		# stretch 下：viewport_px = 物理渲染尺寸，visible.size = 逻辑画布尺寸。
		var logical := Vector2i(int(round(visible.size.x)), int(round(visible.size.y)))
		var mode := str(ProjectSettings.get_setting("display/window/stretch/mode"))
		var aspect := str(ProjectSettings.get_setting("display/window/stretch/aspect"))
		var payload := {
			"physical": [phys.x, phys.y],
			"viewport_px": [viewport_px.x, viewport_px.y],
			"logical": [logical.x, logical.y],
			"render_image": [render_img.get_width(), render_img.get_height()],
			"scale_x": float(phys.x) / float(logical.x),
			"scale_y": float(phys.y) / float(logical.y),
			"stretch_mode": mode,
			"stretch_aspect": aspect,
			"aspect_match": phys.x * logical.y == phys.y * logical.x,
		}
		var f := FileAccess.open(out_json, FileAccess.WRITE)
		if f != null:
			f.store_string(JSON.stringify(payload, "\t"))
			f.close()
		print("WINDOW_PROBE_DONE physical=%dx%d logical=%dx%d scale=%.4f/%.4f mode=%s aspect=%s match=%s"
			% [phys.x, phys.y, logical.x, logical.y, payload["scale_x"], payload["scale_y"],
			   mode, aspect, str(payload["aspect_match"])])
		get_tree().quit(0)


func _init() -> void:
	var out_json := OS.get_environment("CARD_BOXER_WINDOW_JSON")
	if out_json == "":
		print("缺少 CARD_BOXER_WINDOW_JSON")
		quit(1)
		return
	var d := Driver.new()
	d.out_json = out_json
	root.add_child(d)
