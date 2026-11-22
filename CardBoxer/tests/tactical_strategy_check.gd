extends SceneTree
## Opening-style coverage and bounded, public-information decisions.
const AI = preload("res://scripts/tactical_ai.gd")
const Rules = preload("res://scripts/tactical_rules.gd")
const Defs = preload("res://scripts/tactical_defs.gd")
var checks := 0
var failures: Array[String] = []

func _initialize() -> void:
	check_opening_diversity()
	check_last_exchange_scoring()
	check_ranged_choice_and_privacy()
	check_performance()
	for failure in failures:
		print("FAIL: ",failure)
	print("TACTICAL STRATEGY CHECK: %d/%d passed" % [checks-failures.size(),checks])
	quit(0 if failures.is_empty() else 1)

func expect(ok: bool,label: String) -> void:
	checks += 1
	if not ok:
		failures.append(label)

func context() -> Dictionary:
	var ctx: Dictionary = Rules.default_context()
	ctx["decision_seed"] = 2026
	return ctx

func check_opening_diversity() -> void:
	var hand := ["rush","backstep","guard","jab","wave","throw","armored_heavy","focus","cross","parry"]
	var candidates: Array = AI._candidates(hand,context(),"player")
	var styles := {}
	for candidate in candidates:
		var style := String(Defs.card(candidate.ids[0]).ai_style)
		styles[style] = int(styles.get(style,0))+1
	expect(styles.size()==8,"all eight available opening roles survive beam pruning")
	expect(candidates.size()<=24,"five-action search remains bounded to twenty-four full candidates")
	for style in styles:
		expect(int(styles[style])<=3,"one opening role cannot consume more than three full candidate slots")
	for candidate in candidates:
		var slots := {}
		for index in candidate.indices:
			slots[index] = true
		expect(slots.size()==5,"candidate plans consume five different physical cards")

func check_last_exchange_scoring() -> void:
	var evaluator = AI.new()
	expect(evaluator.has_method("_score_state"),"AI has outcome scoring that respects final-exchange resources")
	if not evaluator.has_method("_score_state"):
		return
	var ctx := context()
	ctx.action_count = 1
	ctx.turn = 6
	var guarded: Dictionary = Rules.resolve_exchange(["guard"],["jab"],ctx)
	expect(is_equal_approx(float(evaluator.call("_score_state",ctx,guarded.next_state,"player")),-1.0),"final exchange does not value unusable draw")
	ctx.turn = 1
	guarded = Rules.resolve_exchange(["guard"],["jab"],ctx)
	expect(is_equal_approx(float(evaluator.call("_score_state",ctx,guarded.next_state,"player")),0.0),"earlier successful block values its real next-hand draw")

func check_ranged_choice_and_privacy() -> void:
	var ctx := context()
	ctx.distance = 2
	ctx["opponent_preview"] = ["focus","focus","recover","guard","feint"]
	var hand := ["wave","wave","jab","cross","uppercut","sweep","guard","parry","focus","recover"]
	var chosen: Array = AI.choose_plan(hand,ctx,"player")
	expect(chosen.map(func(index): return hand[index]).has("wave"),"far-distance plan retains a usable ranged attack")
	var original: Dictionary = ctx.duplicate(true)
	ctx["player_hand"] = ["throw","throw"]
	ctx["selected"] = [9,8,7,6,5]
	ctx["locked_plan"] = ["armored_heavy"]
	expect(AI.choose_plan(hand,ctx,"player")==chosen,"unrelated hidden fields do not change a public-information decision")
	ctx.erase("player_hand")
	ctx.erase("selected")
	ctx.erase("locked_plan")
	expect(ctx==original,"AI simulations do not mutate their input")

func check_performance() -> void:
	var hand := ["rush","backstep","guard","jab","wave","throw","armored_heavy","focus","cross","parry"]
	var samples: Array[float] = []
	for seed_value in range(20):
		var ctx := context()
		ctx.decision_seed = seed_value+101
		var started := Time.get_ticks_usec()
		var plan: Array = AI.choose_plan(hand,ctx,"foe")
		samples.append(float(Time.get_ticks_usec()-started)/1000.0)
		expect(plan.size()==5,"ten-card decisions remain legal across seeds")
	samples.sort()
	print("TACTICAL AI P95: %.2fms" % samples[18])
	expect(samples[18]<=500.0,"ten-card AI P95 stays below five hundred milliseconds")
