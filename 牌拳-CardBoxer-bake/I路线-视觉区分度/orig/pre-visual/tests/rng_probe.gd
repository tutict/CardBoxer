extends SceneTree
## 坐实「构造 RandomNumberGenerator 会不会消耗全局随机序列」。
## 旧 _build_backdrop() 在 _ready() 里构造过一个 RNG 实例；删掉它若让
## 后续 randf() 序列偏移一位，就能解释注入态截帧里手牌不同的现象。
##
## 跑法：godot --headless --path . --script res://tests/rng_probe.gd


func _initialize() -> void:
	# 不调 seed()：看引擎启动时全局随机序列是否每次运行都不同。
	var u := randf()
	seed(20261031)
	var a := randf()
	seed(20261031)
	var r := RandomNumberGenerator.new()
	r.seed = 20261031
	var b := randf()
	seed(20261031)
	var c := randf()
	print("RNG_PROBE unseeded=%.9f a=%.9f b=%.9f c=%.9f new_consumes_global=%s reset_restores=%s"
		% [u, a, b, c, str(a != b), str(a == c)])
	quit(0)
