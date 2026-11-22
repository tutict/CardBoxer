extends SceneTree
## Behavioral regressions: actual startup/recovery, defense timing and conditional chains.
const Rules = preload("res://scripts/tactical_rules.gd")
var checks := 0
var failures: Array[String] = []

func _initialize() -> void:
	check_impact_and_waiting_armor()
	check_recovery_windows()
	check_defense_windows_and_baits()
	check_range_and_chase()
	check_conditional_chains()
	check_purity_and_mirrors()
	for failure in failures:
		print("FAIL: ",failure)
	print("TACTICAL TIMING CHECK: %d/%d passed" % [checks-failures.size(),checks])
	quit(0 if failures.is_empty() else 1)

func expect(ok: bool,label: String) -> void:
	checks += 1
	if not ok:
		failures.append(label)

func context(count: int = 1,distance: int = 1) -> Dictionary:
	var ctx: Dictionary = Rules.default_context()
	ctx.action_count = count
	ctx.distance = distance
	return ctx

func combat(p: Array,e: Array,ctx: Dictionary = {}) -> Dictionary:
	return Rules.resolve_exchange(p,e,context(p.size()) if ctx.is_empty() else ctx)

func hits(result: Dictionary,kind: String = "") -> Array:
	var out: Array = []
	for beat in result.get("events",[]):
		for group in beat.groups:
			for hit in group.hits:
				if kind == "" or hit.kind == kind:
					out.append(hit)
	return out

func first(result: Dictionary,kind: String) -> Dictionary:
	var found: Array = hits(result,kind)
	return {} if found.is_empty() else found[0]

func action(result: Dictionary,role: String,index: int = 0) -> Dictionary:
	return result.events[index].actions[role] if result.events.size()>index else {}

func check_impact_and_waiting_armor() -> void:
	var light := combat(["jab"],["armored_heavy"])
	expect(not first(light,"counter").get("interrupt",true),"light counter cannot interrupt armored startup")
	expect(light.next_state.player.hp == 90 and light.next_state.foe.hp == 95,"armor trades damage, never grants damage immunity")
	var strong := combat(["guard_break"],["armored_heavy"])
	expect(first(strong,"counter").get("interrupt",false),"sufficient impact interrupts armored startup")
	expect(strong.next_state.player.hp == 100,"interrupted heavy never contacts")
	var boosted := context()
	boosted.player.jokers = ["counter","triple","sequence"]
	var damage_boost := combat(["jab"],["armored_heavy"],boosted)
	expect(first(damage_boost,"counter").get("damage",0)>5 and not first(damage_boost,"counter").get("interrupt",true),"talent damage does not increase impact")
	var sweep := combat(["jab"],["sweep"])
	expect(sweep.next_state.player.hp == 94,"sweep's stun guard survives a light startup check")
	var waiting := context()
	waiting.foe["ready_delay"] = 6
	var punished := combat(["jab"],["armored_heavy"],waiting)
	expect(first(punished,"punish").get("damage",0)==7,"waiting armor remains punishable before its startup")
	expect(first(punished,"punish").get("interrupt",false) and punished.next_state.player.hp==100,"armor does not protect waiting frames")
	var close := combat(["throw"],["armored_heavy"],context(1,0))
	expect(first(close,"counter").get("interrupt",false),"throw breaks active stun guard")

func check_recovery_windows() -> void:
	var dodge := combat(["sidestep"],["jab"])
	expect(dodge.next_state.player.get("ready_delay",-1)==0 and dodge.next_state.foe.get("ready_delay",-1)==4,"light whiff gives a four-frame next-beat window")
	var next: Dictionary = dodge.next_state.duplicate(true)
	next.turn = 2
	var too_slow := combat(["cross"],["guard"],next)
	expect(hits(too_slow,"punish").is_empty() and hits(too_slow,"blocked").size()==1,"six-frame cross cannot punish a four-frame opening")
	var parry := combat(["parry"],["jab"])
	expect(parry.next_state.foe.get("ready_delay",-1)==10,"parry earns a larger ten-frame punish window")
	var riposte := combat(["cross"],["guard"],parry.next_state)
	expect(first(riposte,"punish").get("damage",0)==9,"cross uses its real startup to punish parry recovery")
	expect(action(riposte,"player").get("start",0)==6,"punish never sets startup to zero")
	var old_flag := context()
	old_flag.foe.exposed = true
	var no_window := combat(["uppercut"],["jab"],old_flag)
	expect(hits(no_window,"punish").is_empty(),"legacy exposed flag cannot manufacture an opening")
	var block := combat(["uppercut"],["guard"],context(1,0))
	expect(block.next_state.player.get("ready_delay",-1)==8,"blocked finisher leaves eight frames of recovery")
	var quick := combat(["cross"],["guard"],block.next_state)
	expect(hits(quick,"punish").is_empty(),"disadvantaged attacker cannot claim the opponent's recovery")
	var flip: Dictionary = context(1,0)
	flip.foe = block.next_state.player.duplicate(true)
	var defender_punish := combat(["cross"],["uppercut"],flip)
	expect(first(defender_punish,"punish").get("damage",0)==9,"defender can punish the unsafe blocked finisher")
	var oversized := context()
	oversized.foe["ready_delay"] = 100
	var capped := combat(["jab"],["guard"],oversized)
	expect(action(capped,"foe").get("wait",-1)==12,"imported recovery delay is bounded to twelve")
	var recover_ctx := context()
	recover_ctx.player["ready_delay"] = 8
	var release := combat(["recover"],["jab"],recover_ctx)
	expect(action(release,"player").get("wait",-1)==4 and release.next_state.player.hp<100,"recover reduces four waiting frames without immunity")

func check_defense_windows_and_baits() -> void:
	var delayed := combat(["sidestep"],["delayed_heavy"])
	expect(hits(delayed,"dodged").is_empty() and delayed.next_state.player.hp==91,"late heavy catches an expired dodge window")
	var shifted := context()
	shifted.player["ready_delay"] = 3
	var timed_parry := combat(["parry"],["delayed_heavy"],shifted)
	expect(hits(timed_parry,"parried").size()==1,"a shifted parry can catch delayed heavy; no immunity tag")
	var wave_dodge := combat(["sidestep"],["wave"],context(1,2))
	expect(hits(wave_dodge,"dodged").size()==1,"nine-frame dodge window includes a ten-frame projectile")
	var wave_parry := combat(["parry"],["wave"],context(1,2))
	expect(hits(wave_parry,"parried").is_empty() and wave_parry.next_state.player.hp<100,"parry's scope excludes projectiles")
	var bait := combat(["feint"],["guard"])
	expect(bait.next_state.foe.get("ready_delay",-1)==6,"active defense bait creates six recovery frames")
	var expired := context()
	expired.player["ready_delay"] = 8
	var empty_bait := combat(["feint"],["sidestep"],expired)
	expect(not empty_bait.next_state.foe.exposed,"feint cannot bait an expired defense")
	var pending := context()
	pending.foe["ready_delay"] = 5
	var early_bait := combat(["feint"],["sidestep"],pending)
	expect(action(early_bait,"foe").get("ready_at",-1)==13,"feint cannot bait a defense still in startup")
	var guard := combat(["guard","guard"],["jab","jab"])
	expect(guard.next_state.player.extra_draw==1,"first successful block grants exactly one next-hand draw")
	var empty_guard := combat(["guard"],["focus"])
	expect(empty_guard.next_state.player.extra_draw==0,"empty guard grants no draw")
	var no_carry := combat(["sidestep","cross"],["jab","jab"],context(2,0))
	expect(hits(no_carry,"dodged").size()==1,"dodge protection never carries into an attacking beat")

func check_range_and_chase() -> void:
	var wave_close := combat(["wave"],["recover"],context(1,0))
	expect(hits(wave_close,"whiff").size()==1 and wave_close.next_state.foe.hp==100,"projectile has a real minimum range")
	var sweep_close := combat(["sweep"],["focus"],context(1,0))
	expect(hits(sweep_close,"whiff").size()==1,"sweep is a middle-distance control tool")
	var sweep_mid := combat(["sweep"],["focus"])
	expect(sweep_mid.next_state.distance==2,"unblocked sweep pushes one distance farther")
	var chase := combat(["sweep","pursuit"],["focus","focus"])
	expect(chase.next_state.distance==1 and action(chase,"player",1).get("pursuit",false),"linked pursuit closes the sweep-created gap")
	expect(action(chase,"player",1).get("combo_applied",false) and hits(chase,"punish").size()==1,"projected chase range qualifies before contact")
	# Cross would contact at4 before backstep6; a linked breaker contacts at7.
	var evade := combat(["jab","guard_break"],["focus","backstep"])
	expect(action(evade,"player",1).get("combo_applied",false) and hits(evade,"whiff").size()==1,"pre-contact movement can spoil a frozen link without rescheduling")

func check_conditional_chains() -> void:
	var linked := combat(["jab","cross","uppercut"],["focus","focus","focus"],context(3,0))
	expect(action(linked,"player",1).get("start",0)==4 and action(linked,"player",2).get("start",0)==6,"starter-linker-ender earns the two-frame discounts")
	expect(action(linked,"player",1).get("combo_cost",0)==1 and action(linked,"player",2).get("combo_cost",0)==2,"links and finishers spend their distinct costs")
	expect(not linked.next_state.player.get("combo",{}).get("open",true),"finisher closes the chain")
	var neutral := combat(["pursuit","uppercut"],["focus","focus"],context(2,0))
	expect(action(neutral,"player",1).get("start",0)==8 and not action(neutral,"player",1).get("combo_applied",true),"neutral linker does not grant an unearned finisher discount")
	expect(neutral.next_state.foe.hp<95,"ineligible finisher still executes its base attack")
	var budget := combat(["jab","cross","cross","uppercut","cross"],["focus","focus","focus","focus","focus"],context(5,0))
	expect(not action(budget,"player",3).get("combo_applied",true) and action(budget,"player",3).get("combo_cost",-1)==0,"a two-point finisher cannot exceed the four-point budget")
	expect(action(budget,"player",3).get("start",0)==8,"budget failure keeps the ordinary finisher startup")
	var reopened := combat(["jab","uppercut","jab","cross","uppercut"],["focus","recover","focus","feint","recover"],context(5,0))
	expect(reopened.events[2].after.player.combo.used==4,"new starter uses remaining exchange budget rather than refunding previous points")
	expect(not action(reopened,"player",3).combo_applied and action(reopened,"player",3).start==6,"reopening a chain cannot exceed four total points in one exchange")
	var broken := combat(["jab","guard","cross"],["focus","focus","focus"],context(3,0))
	expect(not action(broken,"player",2).get("combo_applied",true),"defense deliberately interrupts a chain")
	var trade := combat(["jab","cross"],["jab","focus"],context(2,0))
	expect(action(trade,"player",1).get("start",0)==6 and not action(trade,"player",1).get("combo_applied",true),"simultaneous trade cannot open a combo")
	var next: Dictionary = linked.next_state.duplicate(true)
	next.action_count = 1
	next.turn = 2
	var fresh := combat(["cross"],["focus"],next)
	expect(not action(fresh,"player").get("combo_applied",true),"chains never cross an exchange boundary")
	var last_starter := combat(["guard","recover","feint","focus","jab"],["guard","recover","feint","focus","focus"],context(5,0))
	expect(last_starter.events.back().after.player.combo.open,"last starter really opens a chain inside its own beat")
	expect(not last_starter.next_state.player.combo.open and last_starter.next_state.player.combo.used==0,"returned next-exchange state cannot advertise an expired combo budget")

func check_purity_and_mirrors() -> void:
	var ctx := context(3,1)
	ctx.player["ready_delay"] = 3
	ctx.foe["ready_delay"] = 1
	var before: Dictionary = ctx.duplicate(true)
	var a := combat(["sweep","pursuit","guard_break"],["jab","backstep","wave"],ctx)
	expect(ctx==before,"timing simulation never mutates its caller")
	var reverse := context(3,1)
	reverse.player = ctx.foe.duplicate(true)
	reverse.foe = ctx.player.duplicate(true)
	var b := combat(["jab","backstep","wave"],["sweep","pursuit","guard_break"],reverse)
	expect(a.next_state.player.hp==b.next_state.foe.hp and a.next_state.foe.hp==b.next_state.player.hp,"timed combat is side-neutral")
	expect(a.next_state.distance==b.next_state.distance,"simultaneous distance effects are side-neutral")
	for role in ["player","foe"]:
		for beat in a.events:
			expect(beat.actions[role].start>0,"all contacts retain positive startup")
			expect(beat.after[role].get("ready_delay",-1)>=0 and beat.after[role].get("ready_delay",13)<=12,"each resulting wait is bounded")
