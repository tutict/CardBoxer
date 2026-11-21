extends SceneTree
## 临时微基准：同一份绘制输入快照，str() 与 hash() 各跑 20000 次。
## 用来判断「快照本身会不会比它省下的 _draw() 还贵」。

const N := 20000


func _initialize() -> void:
	var data := [
		0.0, 430.0, 850.0, 0.0, 0.0, 0.0, 0.0,
		[], [], -1.0, "", false,
		["jab", "cross", "guard", "wave", "uppercut"],
		[0.0, 0.0, 0.0, 0.0, 0.0],
		{}, {}, 1, 3, 60.0, [0, 0],
		"taikou", "select", [], 100, 100, 0.0, 0.0, "你", "青岚",
	]
	var t0 := Time.get_ticks_usec()
	var sink_str := ""
	for i in range(N):
		sink_str = str(data)
	var t1 := Time.get_ticks_usec()
	var sink_hash := 0
	for i in range(N):
		sink_hash = hash(data)
	var t2 := Time.get_ticks_usec()
	var us_str := float(t1 - t0) / float(N)
	var us_hash := float(t2 - t1) / float(N)
	print("KEY_BENCH N=%d str_us=%.4f hash_us=%.4f ratio=%.2f sink=%d/%d"
		% [N, us_str, us_hash, us_str / maxf(us_hash, 0.0001),
		   sink_str.length(), sink_hash])
	quit(0)
