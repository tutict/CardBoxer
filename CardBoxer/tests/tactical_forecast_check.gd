extends SceneTree
## Real resolver forecasts, concealed-card privacy and background-job lifecycle.
const Rules = preload("res://scripts/tactical_rules.gd")
const Match = preload("res://scripts/tactical_match.gd")
var Forecast
var checks := 0
var failures: Array[String] = []

func _initialize() -> void:
	call_deferred("run")

func expect(ok: bool,label: String) -> void:
	checks += 1
	if not ok:
		failures.append(label)

func finish() -> void:
	for failure in failures:
		print("FAIL: ",failure)
	print("TACTICAL FORECAST CHECK: %d/%d passed" % [checks-failures.size(),checks])
	quit(0 if failures.is_empty() else 1)

func run() -> void:
	expect(ResourceLoader.exists("res://scripts/tactical_forecast.gd"),"pure public-information forecast module exists")
	if not ResourceLoader.exists("res://scripts/tactical_forecast.gd"):
		finish()
		return
	Forecast = load("res://scripts/tactical_forecast.gd")
	if Forecast==null or not Forecast.can_instantiate():
		expect(false,"forecast module compiles")
		finish()
		return
	check_fillings_and_privacy()
	check_known_defense_and_ko()
	check_performance()
	await check_background_lifecycle()
	finish()

func plan() -> Array:
	return ["jab","cross","guard","sidestep","recover"]

func check_fillings_and_privacy() -> void:
	var ctx: Dictionary = Rules.default_context()
	var preview := ["guard",null,"focus",null,"recover"]
	var original: Dictionary = ctx.duplicate(true)
	var input: Array = preview.duplicate()
	var result: Dictionary = Forecast.forecast_plan(plan(),preview,ctx)
	expect(not result.has("error") and result.sample_count==321,"two-mask filling respects two copies of each of three visible IDs")
	expect(result.beats.size()==5,"forecast covers all five action slots")
	expect(ctx==original and preview==input,"forecast never mutates public inputs")
	var duplicated := ["guard",null,"guard",null,"focus"]
	var limited: Dictionary = Forecast.forecast_plan(plan(),duplicated,ctx)
	expect(limited.sample_count==288,"two visible guards remove guard from concealed candidates")
	ctx["enemy_hand"] = ["armored_heavy","throw"]
	ctx["locked_plan"] = ["guard","throw","focus","armored_heavy","recover"]
	ctx.foe["private_plan"] = ["throw","throw"]
	var concealed: Dictionary = Forecast.forecast_plan(plan(),preview,ctx)
	expect(concealed==result,"private hand and locked plan cannot influence a forecast")
	var serialized := JSON.stringify(concealed)
	expect(not serialized.contains("armored_heavy") and not serialized.contains('"throw"'),"forecast output never contains simulated concealed card identities")
	var incomplete: Dictionary = Forecast.forecast_plan(plan().slice(0,4),preview,ctx)
	expect(incomplete.has("error") and incomplete.beats.is_empty(),"partial selections do not receive a false full-plan prediction")
	var invalid: Dictionary = Forecast.forecast_plan(plan(),["guard",null,"guard",null,"guard"],ctx)
	expect(invalid.has("error"),"impossible visible physical multiplicity is rejected")

func check_known_defense_and_ko() -> void:
	var ctx: Dictionary = Rules.default_context()
	var guarded: Dictionary = Forecast.forecast_plan(["guard","parry","focus","recover","backstep"],["jab","cross","feint","focus","wave"],ctx)
	expect(guarded.sample_count==1 and guarded.beats[0].kinds==["guarded"],"known incoming jab gives a definite block outcome")
	expect(guarded.beats[1].kinds==["parry_success"],"known ordinary melee attack yields a definite parry")
	ctx.player.ready_delay = 2
	ctx.foe.ready_delay = 6
	var window: Dictionary = Forecast.forecast_plan(plan(),["recover","guard","feint","focus","wave"],ctx)
	expect(window.beats[0].get("window_min",-1)==2 and window.beats[0].get("window_max",-1)==2,"forecast explains the actual window after recover reduces waiting")
	expect(window.beats[0].get("start_min",-1)==6 and window.beats[0].get("start_max",-1)==6,"forecast displays actual contact timing including own wait")
	ctx.player.ready_delay = 0
	ctx.foe.ready_delay = 0
	ctx.player.hp = 3
	ctx.foe.hp = 3
	var ko: Dictionary = Forecast.forecast_plan(["jab","cross","guard","sidestep","recover"],["jab",null,"guard",null,"focus"],ctx)
	expect(ko.beats[1].kinds==["skipped"] and ko.beats[4].kinds==["skipped"],"terminal first-beat trade marks later actions unexecuted")

func check_performance() -> void:
	var samples: Array[float] = []
	for index in range(20):
		var ctx: Dictionary = Rules.default_context()
		ctx.player.ready_delay = index%4
		ctx.foe.ready_delay = index%3
		var started := Time.get_ticks_usec()
		var result: Dictionary = Forecast.forecast_plan(plan(),["guard",null,"focus",null,"recover"],ctx)
		samples.append(float(Time.get_ticks_usec()-started)/1000.0)
		expect(result.sample_count<=324,"forecast never exceeds the bounded concealed search")
	samples.sort()
	print("TACTICAL FORECAST P95: %.2fms" % samples[18])
	expect(samples[18]<=1000.0,"full forecast P95 stays under one second")

func wait_forecast(m) -> void:
	var deadline := Time.get_ticks_msec()+3000
	while Time.get_ticks_msec()<deadline and m.forecast_status=="pending":
		m.tick(0.0)
		OS.delay_msec(2)
		await process_frame

func check_background_lifecycle() -> void:
	var m = Match.new(41)
	for index in [0,1,2]:
		m.toggle(index)
	m.confirm()
	m.tick(1.1)
	expect(m.has_method("request_forecast"),"match owns a nonblocking forecast lifecycle")
	if not m.has_method("request_forecast"):
		return
	for index in [0,1,2,3,4]:
		m.toggle(index)
	var state: Dictionary = m.state.duplicate(true)
	m.request_forecast()
	await wait_forecast(m)
	expect(m.forecast_status=="ready" and m.forecast.sample_count>0,"completed background forecast is published for the current selection")
	expect(m.state==state,"background forecast never applies simulated damage")
	var original: Dictionary = m.forecast.duplicate(true)
	m.move_selected(0,1)
	expect(m.forecast.is_empty(),"changing selection immediately removes the old visible forecast")
	m.request_forecast()
	await wait_forecast(m)
	var current_plan: Array = m.selected.map(func(index): return m.hand[index])
	var expected: Dictionary = Forecast.forecast_plan(current_plan,m.enemy_preview,m.public_context("player"))
	expect(m.forecast==expected,"only the latest selected-order result is displayed")
	m.move_selected(1,0)
	m.request_forecast()
	expect(m.forecast_status=="ready" and m.forecast==original,"returning to a previous public snapshot uses its cached result")
	m.undo()
	m.toggle(7)
	m.request_forecast()
	m.restart(41)
	var deadline := Time.get_ticks_msec()+3000
	while Time.get_ticks_msec()<deadline and int(m._forecast_task)>=0:
		m.tick(0.0)
		OS.delay_msec(2)
		await process_frame
	expect(m.phase=="loadout" and m.forecast.is_empty() and m.forecast_status=="idle","restart cannot publish an older selection's forecast")
