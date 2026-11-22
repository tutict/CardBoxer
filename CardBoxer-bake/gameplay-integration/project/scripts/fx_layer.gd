extends Node2D
## 特效与投射物的独立绘制层。
##
## 必须单独成层：父节点的 _draw 永远画在子节点之前，所以把火花直接画在
## arena._draw 里，它们会被两个角色盖住 —— 伤害数字就是这么消失的。
## 这一层排在角色之后、界面之前。

var arena = null


func _draw() -> void:
	if arena == null:
		return
	var t0 := Time.get_ticks_usec()
	arena.redraw_stats["fx_draws"] = int(arena.redraw_stats["fx_draws"]) + 1
	arena.paint_fx(self)
	arena.paint_projectiles(self)
	arena.redraw_stats["fx_draw_us"] = int(arena.redraw_stats["fx_draw_us"]) + (Time.get_ticks_usec() - t0)
