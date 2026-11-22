extends SceneTree
## Feedback must describe executed contacts without revealing future outcomes.
const Match = preload("res://scripts/tactical_match.gd")
const Rules = preload("res://scripts/tactical_rules.gd")
var failures: Array[String] = []
var checks := 0

func _initialize() -> void:
	check_contact_distance()
	check_interruption_timing()
	check_range_miss()
	check_defense_perspective()
	check_defense_failures()
	check_recap_lifecycle()
	check_ko_feedback()
	for failure in failures:
		print("FAIL: ",failure)
	print("TACTICAL FEEDBACK CHECK: %d/%d passed" % [checks-failures.size(),checks])
	quit(0 if failures.is_empty() else 1)

func expect(ok: bool,label: String) -> void:
	checks += 1
	if not ok:
		failures.append(label)

func playback(player_first: String,foe_first: String,distance: int = 1,foe_hp: int = 100):
	var m = Match.new(2026)
	for index in [0,1,2]:
		m.toggle(index)
	m.confirm()
	m.tick(1.1)
	m.state = Rules.default_context()
	m.state.distance = distance
	m.state.foe.hp = foe_hp
	m.player_plan = [player_first,"focus","recover","backstep","guard"]
	m.enemy_plan = [foe_first,"focus","recover","backstep","guard"]
	m._begin_resolve()
	return m

func feedback(m,role: String,index: int = 0) -> Dictionary:
	return m.feedback_for(role,index) if m.has_method("feedback_for") else {}

func summary(m) -> String:
	return m.last_exchange_summary() if m.has_method("last_exchange_summary") else ""

func check_contact_distance() -> void:
	var m = playback("sweep","focus")
	m.tick(0.60)
	var hit: Dictionary = m.latest_hits[0]
	expect(hit.get("distance",-1)==1,"contact describes middle reach before sweep pushes to far")
	expect(hit.get("frame",-1)==8,"contact exposes the actual executed frame")
	expect(m.state.distance==2,"distance fixture really changes after the contact")

func check_interruption_timing() -> void:
	var m = playback("uppercut","jab")
	expect(m.has_method("feedback_for"),"controller exposes executed action feedback")
	expect(feedback(m,"player").is_empty(),"precomputed cancelled action stays unknown before playback")
	m.tick(0.439)
	expect(feedback(m,"player").is_empty(),"startup result stays unknown immediately before contact")
	m.paused = true
	m.tick(20.0)
	expect(feedback(m,"player").is_empty(),"pause cannot publish a future interruption")
	m.paused = false
	m.tick(0.001)
	var actual := feedback(m,"player")
	expect(actual.get("kind","")=="interrupted","incoming hit publishes the cancelled action despite no outgoing contact")
	expect(actual.get("label","").contains("打断"),"cancelled action is named as interrupted")
	expect(actual.get("reason","").contains("4") and actual.get("reason","").contains("8"),"interruption explains the opponent's earlier contact versus planned startup")
	var frozen := actual.duplicate(true)
	m._advance_schedule(m.resolution_time)
	expect(feedback(m,"player")==frozen,"same scheduled contact cannot duplicate or change feedback")
	expect(feedback(m,"foe").get("damage",0)==5,"attacker feedback preserves actual counter damage")
	expect(feedback(m,"player",4).is_empty(),"later beats stay unknown after the first contact")

func check_range_miss() -> void:
	var m = playback("throw","guard")
	m.tick(0.48)
	var actual := feedback(m,"player")
	expect(actual.get("kind","")=="whiff" and actual.get("damage",-1)==0,"zero-damage range miss receives an outcome")
	expect(actual.get("reason","").contains("中距") and actual.get("reason","").contains("贴身"),"range miss explains actual distance and required reach")
	expect(m.audit.size()==1 and m.audit[0].kind=="whiff","feedback does not create a phantom damage contact")

func check_defense_perspective() -> void:
	for fixture in [["sidestep","jab",1,0.44,"evaded","dodged","闪避"],["parry","uppercut",0,0.60,"parry_success","parried","招架"]]:
		var m = playback(fixture[0],fixture[1],fixture[2])
		m.tick(float(fixture[3]))
		var defender := feedback(m,"player")
		var attacker := feedback(m,"foe")
		expect(defender.get("kind","")==fixture[4],"successful defense is credited to its owner: "+fixture[0])
		expect(attacker.get("kind","")==fixture[5],"defeated attack retains its actual contact kind: "+fixture[0])
		expect(defender.get("label","").contains("成功"),"defender sees a successful defensive action: "+fixture[0])
		expect(attacker.get("label","").begins_with("被"),"attacker sees that its attack was avoided: "+fixture[0])
		expect(not m.combat_log.is_empty() and m.combat_log.back().contains("被"+String(fixture[6])),"source attack log uses attacker perspective: "+fixture[0])

func check_defense_failures() -> void:
	var late = playback("sidestep","delayed_heavy")
	late.tick(0.76)
	var expired := feedback(late,"player")
	expect(expired.get("kind","")=="defense_expired","late heavy contact explains an expired dodge")
	expect(expired.get("reason","").contains("12") and expired.get("reason","").contains("2–10"),"expired dodge explanation uses the exclusive window end correctly")
	var bypass = playback("guard","throw",0)
	bypass.tick(0.48)
	var blocked := feedback(bypass,"player")
	expect(blocked.get("kind","")=="defense_bypassed","throw explains why the completed guard did not stop it")
	expect(blocked.get("reason","").contains("投技") and blocked.get("reason","").contains("格挡"),"bypassed guard names the relevant matchup")

func check_recap_lifecycle() -> void:
	var m = playback("uppercut","jab")
	m.tick(100.0)
	expect(m.phase=="select" and m.turn_index==2,"feedback fixture reaches the following planning phase")
	var recap := summary(m)
	expect(recap.contains("造成0") and recap.contains("受伤5"),"completed recap retains both actual damage totals")
	expect(recap.contains("1被打断"),"completed recap keeps the missed action's beat after refill")
	var before := recap
	m.toggle(0)
	m.tick(0.0)
	expect(summary(m)==before,"editing the next plan cannot overwrite the preceding result")
	m.restart(2026)
	expect(summary(m)=="" and feedback(m,"player").is_empty(),"restart clears the previous result and live outcomes")

func check_ko_feedback() -> void:
	var m = playback("jab","focus",1,1)
	m.tick(100.0)
	expect(m.phase=="round_over","single-contact KO stops the exchange")
	expect(feedback(m,"player",1).get("kind","")=="skipped","KO marks later plan slots as unexecuted after playback ends")
	expect(summary(m).contains("造成1") and summary(m).contains("2未执行"),"KO recap records effective damage and skipped beats")
