extends RefCounted
## Independent visual clocks. No rule, meter, collision or RNG changes occur here.
signal cue_ready(impact: Dictionary)
const Defs = preload("res://scripts/card_data.gd")
const CONTACT_S := 0.48
const ATTACK_S := 1.12
const CONTACT_HOLD_S := 0.24
const KO_S := 0.45
const BLEND_S := 0.06
const RETREAT_START_S := 0.56
const GAIT_STRIDE_PX := 120.0
var library = null
var round_id := 0
var exchange: Dictionary = {}
var exchange_time := 0.0
var contact_emitted := false
var _hold_left := 0.0
var _remainder := 0.0
var _seen: Dictionary = {}
var _latches: Dictionary = {}
var _reactions: Dictionary = {}
var _terminal: Dictionary = {}
var _terminal_attacks: Dictionary = {}
var _fresh_latches: Dictionary = {}
var _idle_time := 0.0
var _last_poses: Dictionary = {}
var _last_pose_keys: Dictionary = {}
var _transitions: Dictionary = {}

func setup(p_library) -> void:
	library = p_library
	if library != null and library.available(): library.prepare_support()

func reset(p_round_id: int) -> void:
	round_id = p_round_id
	exchange.clear()
	exchange_time = 0.0
	contact_emitted = false
	_hold_left = 0.0
	_remainder = 0.0
	_seen.clear()
	_latches.clear()
	_reactions.clear()
	_terminal.clear()
	_terminal_attacks.clear()
	_fresh_latches.clear()
	_idle_time = 0.0
	_last_poses.clear()
	_last_pose_keys.clear()
	_transitions.clear()

func begin_exchange(event: Dictionary) -> void:
	if int(event.get("round_id", round_id)) != round_id: return
	var identity := str(["exchange", round_id, event.get("actor", ""), event.get("action_seq", 0), event.get("winner", "")])
	if _seen.has(identity): return
	_seen[identity] = true
	exchange = event.duplicate(true)
	exchange_time = 0.0
	contact_emitted = false
	_hold_left = 0.0
	_remainder = 0.0
	_reactions.clear()
	if String(exchange.get("winner", "")) == "draw":
		contact_emitted = true
		for impact: Dictionary in exchange.get("impacts", []):
			_start_reaction(impact)
			cue_ready.emit(impact.duplicate(true))

func record_impact(impact: Dictionary) -> void:
	if int(impact.get("round_id", round_id)) != round_id: return
	var key := str([round_id, impact.get("actor", ""), impact.get("target", ""), impact.get("action_seq", 0), impact.get("source_kind", "melee")])
	if _seen.has(key): return
	_seen[key] = true
	if String(impact.get("source_kind", "")) != "release": _start_reaction(impact)
	if not bool(impact.get("dodged", false)) and String(impact.get("source_kind", "")) != "projectile":
		_latches[String(impact.get("actor", "player"))] = impact.duplicate(true)
		_fresh_latches[String(impact.get("actor", "player"))] = true
	if bool(impact.get("terminal", false)) and String(impact.get("source_kind", "")) != "projectile":
		var card: Dictionary = Defs.card(String(impact.get("clip_id", "")))
		_terminal_attacks[String(impact.get("actor", "player"))] = {"time":0.0,"duration":float(card.get("recover",1)) * Defs.FRAME,"hold_left":float(impact.get("local_hitstop",0.0)),"impact":impact.duplicate(true)}

func _start_reaction(impact: Dictionary) -> void:
	if bool(impact.get("dodged", false)): return
	var role := String(impact.get("target", "foe"))
	var duration := float(impact.get("stun_duration", 0.26))
	var clip := "block" if bool(impact.get("blocked", false)) else ("hit_heavy" if duration > 0.26 else "hit_light")
	_reactions[role] = {"clip_id":clip,"time":0.0,"duration":duration,"impact":impact.duplicate(true)}
	if bool(impact.get("terminal", false)):
		_terminal[role] = {"time":0.0,"hold_left":float(impact.get("local_hitstop",0.0)) if String(impact.get("source_kind","")) != "taikou" else 0.0,"impact":impact.duplicate(true)}

## Save currently playing winner actions before Arena freezes its rule state.
## A late fatal projectile may belong to an older action; keep the current clip.
func capture_terminal(snapshots: Dictionary) -> void:
	for role: String in snapshots:
		var snapshot: Dictionary = snapshots[role]
		if _terminal.has(role) or _terminal_attacks.has(role) or int(snapshot.get("state",0)) != 1: continue
		var clip := String(snapshot.get("card_id",""))
		var card: Dictionary = Defs.card(clip)
		if card.is_empty(): continue
		var phases := ["windup","active","recover"]
		var phase_index := phases.find(String(snapshot.get("phase","windup")))
		var duration := -float(snapshot.get("phase_time",0.0))
		for index in range(maxi(phase_index,0),3): duration += float(card[phases[index]]) * Defs.FRAME
		_terminal_attacks[role] = {"time":0.0,"duration":maxf(duration,0.001),"hold_left":float(snapshot.get("local_hitstop",0.0)),"impact":{"clip_id":clip},"snapshot":snapshot.duplicate(true)}

func advance(dt: float, context: Dictionary) -> void:
	if bool(context.get("pause", false)): return
	_fresh_latches.clear()
	dt = maxf(dt, 0.0)
	var global_hold := float(context.get("global_hitstop", 0.0)) > 0.0
	if _hold_left > 0.0:
		_remainder += maxf(0.0, dt - _hold_left)
		_hold_left = maxf(0.0, _hold_left - dt)
		return
	if global_hold: return
	_idle_time += dt
	if String(context.get("mode", "realtime")) == "taikou" and not exchange.is_empty():
		dt += _remainder
		_remainder = 0.0
		var next := exchange_time + dt
		if not contact_emitted and String(exchange.get("winner", "")) != "draw" and next >= CONTACT_S - 0.0000001:
			_remainder = maxf(0.0, next - CONTACT_S)
			exchange_time = CONTACT_S
			contact_emitted = true
			_hold_left = CONTACT_HOLD_S
			for impact: Dictionary in exchange.get("impacts", []):
				_start_reaction(impact)
				cue_ready.emit(impact.duplicate(true))
			return
		exchange_time = next
	var snapshots: Dictionary = context.get("snapshots", {})
	var taikou := String(context.get("mode", "realtime")) == "taikou"
	for role: String in _transitions:
		if float(snapshots.get(role, {}).get("local_hitstop", 0.0)) > 0.0: continue
		_transitions[role]["time"] = minf(BLEND_S, float(_transitions[role]["time"]) + dt)
	for role: String in _reactions:
		var snap: Dictionary = snapshots.get(role, {})
		if not taikou and not bool(context.get("terminal",false)) and float(snap.get("local_hitstop", 0.0)) > 0.0: continue
		_reactions[role]["time"] = float(_reactions[role]["time"]) + dt
	for role: String in _terminal:
		var snap: Dictionary = snapshots.get(role, {})
		if not taikou and not bool(context.get("terminal",false)) and float(snap.get("local_hitstop", 0.0)) > 0.0: continue
		var consumed := minf(dt, float(_terminal[role]["hold_left"]))
		_terminal[role]["hold_left"] = maxf(0.0, float(_terminal[role]["hold_left"]) - consumed)
		_terminal[role]["time"] = minf(KO_S, float(_terminal[role]["time"]) + dt - consumed)
	for role: String in _terminal_attacks:
		var consumed := minf(dt, float(_terminal_attacks[role]["hold_left"]))
		_terminal_attacks[role]["hold_left"] = maxf(0.0, float(_terminal_attacks[role]["hold_left"]) - consumed)
		_terminal_attacks[role]["time"] = float(_terminal_attacks[role]["time"]) + dt - consumed

func sample(role: String, snapshot: Dictionary, context: Dictionary) -> Dictionary:
	if library == null or not library.available(): return {}
	var clip := "idle"
	var frame := 0.0
	var facing := int(snapshot.get("facing", 1 if role == "player" else -1))
	var shift := Vector2.ZERO
	var tilt := 0.0
	var frozen := bool(context.get("pause", false)) or float(context.get("global_hitstop", 0.0)) > 0.0 or float(snapshot.get("local_hitstop", 0.0)) > 0.0 or _hold_left > 0.0
	var taikou := String(context.get("mode", "realtime")) == "taikou"
	if _terminal.has(role):
		clip = "ko"
		frame = float(_terminal[role]["time"]) / KO_S * float(library.clip_frames(role, clip) - 1)
		frozen = bool(context.get("pause",false)) or float(context.get("global_hitstop",0.0)) > 0.0 or _hold_left > 0.0 or float(_terminal[role]["hold_left"]) > 0.0 or float(_terminal[role]["time"]) >= KO_S
	elif _terminal_attacks.has(role):
		var attack: Dictionary = _terminal_attacks[role]
		if float(attack["time"]) < float(attack["duration"]):
			clip = String(attack.impact.get("clip_id","stance"))
			if attack.has("snapshot"):
				frame = _terminal_action_frame(role,clip,attack)
			else:
				frame = lerpf(maxf(0.0,library.contact_frame(role,clip)),float(library.clip_frames(role,clip) - 1),clampf(float(attack["time"]) / float(attack["duration"]),0.0,1.0))
			frozen = frozen or float(attack["hold_left"]) > 0.0
		else:
			clip = "stance"
	elif _reactions.has(role) and (taikou or int(snapshot.get("state",0)) in [2,3]) and float(_reactions[role]["time"]) <= float(_reactions[role]["duration"]):
		var reaction: Dictionary = _reactions[role]
		clip = String(reaction["clip_id"])
		var at := float(reaction["time"])
		if not taikou and int(snapshot.get("state", 0)) in [2, 3]: at = float(snapshot.get("state_time", 0.0))
		frame = clampf(at / float(reaction["duration"]), 0.0, 1.0) * float(library.clip_frames(role, clip) - 1)
	elif taikou and not exchange.is_empty():
		if String(exchange.get("actor", "")) == role and exchange_time <= ATTACK_S:
			clip = String(exchange.get("clip_id", "stance"))
			var contact: float = library.contact_frame(role, clip)
			if exchange_time <= CONTACT_S:
				frame = maxf(contact, 0.0) * clampf(exchange_time / CONTACT_S, 0.0, 1.0)
			else:
				frame = lerpf(maxf(contact, 0.0), float(library.clip_frames(role, clip) - 1), clampf((exchange_time - CONTACT_S) / (ATTACK_S - CONTACT_S), 0.0, 1.0))
		else:
			clip = "stance"
	elif taikou and String(context.get("taikou_phase", "")) == "reveal":
		clip = "focus"
		frame = clampf(float(context.get("taikou_time", 0.0)) / 1.5, 0.0, 1.0) * float(library.clip_frames(role, clip) - 1)
	elif _latches.has(role) and int(_latches[role].get("action_seq", -1)) == int(snapshot.get("action_seq", 0)) and (_fresh_latches.has(role) or _impact_holding(_latches[role], context)):
		clip = String(_latches[role].get("clip_id", "stance"))
		frame = maxf(0.0, library.contact_frame(role, clip))
		frozen = true
	elif int(snapshot.get("state", 0)) == 1 and String(snapshot.get("card_id", "")) != "":
		clip = String(snapshot["card_id"])
		frame = library.phase_frame(role, clip, String(snapshot.get("phase", "windup")), float(snapshot.get("phase_progress", 0.0)))
	elif int(snapshot.get("state", 0)) == 5:
		clip = "ko"
		frame = minf(1.0, float(snapshot.get("state_time", 0.0)) / KO_S) * float(library.clip_frames(role, clip) - 1)
	elif int(snapshot.get("state", 0)) in [2, 3]:
		clip = "block" if int(snapshot["state"]) == 3 else ("hit_heavy" if float(snapshot.get("stun_duration", 0.26)) > 0.26 else "hit_light")
		frame = clampf(float(snapshot.get("state_time", 0.0)) / maxf(0.001, float(snapshot.get("stun_duration", 0.26))), 0.0, 1.0) * float(library.clip_frames(role, clip) - 1)
	elif bool(snapshot.get("guarding", false)):
		clip = "guard"
		frame = float(library.clip_frames(role, clip) - 1)
	elif bool(snapshot.get("dodging", false)):
		clip = "sidestep"
		frame = float(library.clip_frames(role, clip) - 1)
	elif float(snapshot.get("walk_blend", 0.0)) > 0.001:
		clip = "walk"
		var phase := float(snapshot.get("walk_phase", 0.0))
		if int(snapshot.get("walk_direction",1)) < 0: phase = fposmod(-phase,1.0)
		frame = phase * float(library.clip_frames(role, clip) - 1)
	else:
		frame = fposmod(_idle_time * 60.0, float(maxi(library.clip_frames(role, clip) - 1, 1)))
	if taikou and not exchange.is_empty():
		var direction := 1.0 if String(exchange.get("actor", "")) == "player" else -1.0
		var after := maxf(0.0, exchange_time - CONTACT_S)
		if role == String(exchange.get("actor", "")) and exchange_time <= ATTACK_S:
			shift.x = _contact_shift(direction)*_travel_weight(exchange_time)
		elif contact_emitted and String(exchange.get("winner", "")) != "draw":
			var fade := maxf(0.0, 1.0 - after / 0.56)
			shift.x = 40.0 * direction * fade
			tilt = deg_to_rad(9.0) * direction * fade
	var pose: Dictionary = library.sample(role, clip, frame)
	if clip == "walk": pose = _blend_stance(role, pose, float(snapshot.get("walk_blend", 0.0)))
	if taikou and role == String(exchange.get("actor","")) and absf(float(exchange.get("approach_extra_x",0.0))) > 20.0 and exchange_time > 0.0 and exchange_time < ATTACK_S:
		var direction := 1.0 if role == "player" else -1.0
		var travel := absf(_contact_shift(direction))
		var returning := exchange_time > RETREAT_START_S
		var progress := clampf((exchange_time-RETREAT_START_S)/(ATTACK_S-RETREAT_START_S),0.0,1.0) if returning else clampf(exchange_time/CONTACT_S,0.0,1.0)
		var duration := ATTACK_S-RETREAT_START_S if returning else CONTACT_S
		var velocity := travel*30.0*progress*progress*(1.0-progress)*(1.0-progress)/duration
		var signed_travel := -travel*(1.0-_travel_weight(exchange_time)) if returning else travel*_travel_weight(exchange_time)
		# Smooth saturation keeps fast dashes readable without a velocity corner
		# when an arbitrary gait-strength cap is reached.
		pose = _travel_legs(role,pose,signed_travel,.55*(1.0-exp(-velocity/600.0)))
	var contact: float = library.contact_frame(role,clip)
	var immediate := clip in ["hit_light","hit_heavy","block","ko"] or (contact >= 0.0 and is_equal_approx(frame,contact) and frozen)
	var identity := str([context.get("mode","realtime"),clip,snapshot.get("action_seq",0),snapshot.get("state",0),snapshot.get("walk_direction",1) if clip == "walk" else 0])
	pose = _transition_pose(role,pose,identity,immediate)
	return {"pose":pose,"facing":facing,"canvas_shift":shift,"canvas_tilt":tilt,"clip_id":clip,"frame":frame,"frozen":frozen}

func _transition_pose(role: String, target: Dictionary, identity: String, immediate: bool) -> Dictionary:
	if immediate:
		_transitions.erase(role)
	elif _last_poses.has(role) and String(_last_pose_keys.get(role,"")) != identity:
		_transitions[role] = {"from":_last_poses[role].duplicate(true),"time":0.0}
	_last_pose_keys[role] = identity
	var displayed := target
	if _transitions.has(role):
		var transition: Dictionary = _transitions[role]
		var weight := clampf(float(transition["time"]) / BLEND_S,0.0,1.0)
		displayed = _mix_pose(transition["from"],target,weight)
		if weight >= 1.0: _transitions.erase(role)
	_last_poses[role] = displayed.duplicate(true)
	return displayed

func _contact_shift(direction: float) -> float:
	# Keep the existing calibration's exact .48s pulse contribution.
	var peak := 110.0*maxf(0.0,1.0-absf(CONTACT_S/ATTACK_S-.45)/.3)
	return peak*direction+float(exchange.get("approach_extra_x",0.0))

func _smootherstep(progress: float) -> float:
	var p := clampf(progress,0.0,1.0)
	return p*p*p*(p*(p*6.0-15.0)+10.0)

func _travel_weight(time: float) -> float:
	if time <= CONTACT_S: return _smootherstep(time/CONTACT_S)
	# The glove recoils while the torso still owns the contact space, then the
	# feet carry the return. This uses visual world time, so holds freeze it.
	return 1.0-_smootherstep((time-RETREAT_START_S)/(ATTACK_S-RETREAT_START_S))

## Distance, signed relative to facing, drives both approach and retreat. A
## zero velocity produces the authored pose exactly, including contact/guard.
func _travel_legs(role: String, pose: Dictionary, signed_travel: float, weight: float) -> Dictionary:
	if weight <= .000001: return pose
	var phase := fposmod(signed_travel/GAIT_STRIDE_PX,1.0)
	var walk: Dictionary = library.sample(role,"walk",phase*float(library.clip_frames(role,"walk")-1))
	var stance: Dictionary = library.sample(role,"stance",0.0)
	var out: Dictionary = pose.duplicate(true)
	for bone: String in ["thigh_f","shin_f","thigh_b","shin_b"]:
		var a: Array = pose.rotations[bone]
		var b: Array = walk.rotations[bone]
		var s: Array = stance.rotations[bone]
		var delta := Quaternion(s[0],s[1],s[2],s[3]).inverse()*Quaternion(b[0],b[1],b[2],b[3])
		var q := (Quaternion(a[0],a[1],a[2],a[3])*Quaternion.IDENTITY.slerp(delta,clampf(weight,0.0,1.0))).normalized()
		out.rotations[bone] = [q.x,q.y,q.z,q.w]
	return library.preserve_support(role,out,pose)

func _impact_holding(impact: Dictionary, context: Dictionary) -> bool:
	if float(context.get("global_hitstop", 0.0)) > 0.0: return true
	var snapshots: Dictionary = context.get("snapshots", {})
	return float(snapshots.get(String(impact.get("target", "foe")), {}).get("local_hitstop", 0.0)) > 0.0

func _terminal_action_frame(role: String, clip: String, attack: Dictionary) -> float:
	var card: Dictionary = Defs.card(clip)
	var phases := ["windup","active","recover"]
	var index := maxi(0,phases.find(String(attack.snapshot.get("phase","windup"))))
	var elapsed := float(attack.snapshot.get("phase_time",0.0)) + float(attack["time"])
	while index < 3:
		var duration := float(card[phases[index]]) * Defs.FRAME
		if elapsed <= duration and duration > 0.0:
			return library.phase_frame(role,clip,phases[index],clampf(elapsed / duration,0.0,1.0))
		elapsed -= duration
		index += 1
	return float(library.clip_frames(role,clip) - 1)

func _blend_stance(role: String, pose: Dictionary, weight: float) -> Dictionary:
	var stance: Dictionary = library.sample(role, "stance", 0.0)
	return _mix_pose(stance,pose,weight)

func _mix_pose(from: Dictionary, pose: Dictionary, weight: float) -> Dictionary:
	var out: Dictionary = pose.duplicate(true)
	for bone: String in out.get("rotations", {}):
		var a: Array = from.rotations[bone]
		var b: Array = out.rotations[bone]
		var q := Quaternion(a[0],a[1],a[2],a[3]).slerp(Quaternion(b[0],b[1],b[2],b[3]), clampf(weight,0.0,1.0))
		out.rotations[bone] = [q.x,q.y,q.z,q.w]
	for axis in range(3): out.root_offset[axis] = lerpf(float(from.root_offset[axis]), float(pose.root_offset[axis]), clampf(weight,0.0,1.0))
	return out
