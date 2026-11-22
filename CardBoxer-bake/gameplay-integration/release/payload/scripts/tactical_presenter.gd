extends RefCounted
## Samples authored poses from immutable beat events. Never changes combat state.
const Defs = preload("res://scripts/tactical_defs.gd")
const Match = preload("res://scripts/tactical_match.gd")
const BasePresentation = preload("res://scripts/battle_presentation.gd")
const GAPS := [190.0,330.0,480.0]
var library = null
var layers: Dictionary = {}
var beat: Dictionary = {}
var _reactions: Dictionary = {}
var _contact_gaps: Dictionary = {}
var _idle_time := 0.0
var _helper = null

func setup(native_library) -> void:
	library = native_library
	_helper = BasePresentation.new()
	_helper.setup(library)

func reset() -> void:
	beat.clear()
	_reactions.clear()
	_contact_gaps.clear()
	_idle_time = 0.0
	if _helper != null:
		_helper.reset(0)

func advance(delta: float) -> void:
	_idle_time += delta
	if _helper != null:
		_helper.advance(delta,{"mode":"tactical","pause":false})

func begin_beat(event: Dictionary) -> void:
	beat = event.duplicate(true)
	_reactions.clear()
	_contact_gaps.clear()
	for group in beat.groups:
		for hit in group.hits:
			if int(hit.damage)>0 and hit.card_id != "wave":
				_contact_gaps[hit.source] = _desired_gap(hit)

func record_group(group: Dictionary) -> void:
	for hit in group.hits:
		if int(hit.damage)>0:
			_reactions[hit.target] = {"at":float(group.visual_at),"hit":hit.duplicate(true)}

func _smooth(value: float) -> float:
	var t := clampf(value,0.0,1.0)
	return t*t*(3.0-2.0*t)

func _gap(m) -> float:
	if m.phase != "resolve" or beat.is_empty():
		return GAPS[clampi(int(m.state.distance),0,2)]
	var previous: float = GAPS[int(beat.before.distance)]
	var t: float = m.visual_time()
	for contact in beat.get("contacts",[]):
		var target: float = GAPS[int(contact.group.state.distance)]
		if is_equal_approx(target,previous):
			continue
		var at := float(contact.at)
		var weight := _smooth((t-maxf(0.0,at-0.30))/maxf(0.001,minf(at,0.30)))
		if t<at:
			return lerpf(previous,target,weight)
		previous = target
	return previous

func positions(m) -> Dictionary:
	var gap := _gap(m)
	return {"player":Vector2(640.0-gap*0.5,520.0),"foe":Vector2(640.0+gap*0.5,520.0)}

func _travel(t: float, at: float) -> float:
	if t <= at:
		return _smooth(t/maxf(at,0.001))
	return 1.0-_smooth((t-at)/Match.RECOVER_S)

func _desired_gap(hit: Dictionary) -> float:
	if library == null or layers.get(hit.source) == null or layers.get(hit.target) == null:
		return 150.0
	var source_layer = layers[hit.source]
	var target_layer = layers[hit.target]
	var pose: Dictionary = library.sample(hit.source,hit.clip,maxf(0.0,library.contact_frame(hit.source,hit.clip)))
	var react := "block" if hit.kind == "blocked" else ("hit_heavy" if hit.kind in ["counter","punish"] or int(hit.damage)>=8 else "hit_light")
	var victim_pose: Dictionary = library.sample(hit.target,react,0.0)
	var direction := 1.0 if hit.source == "player" else -1.0
	var anchor := "rear_hand" if hit.clip == "cross" else "lead_hand"
	var fist: Vector2 = source_layer.anchor_offset(pose,anchor,int(direction))
	var head: Vector2 = target_layer.anchor_offset(victim_pose,"head",int(-direction),direction*deg_to_rad(7.0))
	var chest: Vector2 = target_layer.anchor_offset(victim_pose,"chest",int(-direction),direction*deg_to_rad(7.0))
	var mix := clampf((fist.y-head.y)/(chest.y-head.y),0.0,1.0) if absf(chest.y-head.y)>0.001 else 0.5
	return clampf((fist.x-head.lerp(chest,mix).x)*direction,-120.0,230.0)

func sample(m,role: String) -> Dictionary:
	var facing := 1 if role == "player" else -1
	var snapshot := {"state":0,"card_id":"","action_seq":int(m.state.round_id)*100+int(m.turn_index)*3,"phase":"","phase_progress":0.0,"state_time":_idle_time,"stun_duration":0.30,"local_hitstop":0.0,"facing":facing,"walk_phase":0.0,"walk_blend":0.0,"moving":false,"walk_direction":1,"guarding":false,"dodging":false,"is_super":false,"hp":int(m.state[role].hp),"frozen":bool(m.paused),"flash":0.0,"canvas_shift":Vector2.ZERO,"canvas_tilt":0.0,"stun_tilt":0.0}
	var active: bool = m.phase == "resolve" and not m.active_beat.is_empty()
	var t: float = m.visual_time() if active else 0.0
	if int(snapshot.hp) <= 0:
		snapshot.state = 5
		snapshot.state_time = float(m.phase_time)
		if active and _reactions.has(role):
			snapshot.state_time = maxf(0.0,t-float(_reactions[role].at))
		if not active:
			snapshot.state_time = maxf(0.75,float(m.phase_time))
			return snapshot
	if m.phase == "reveal":
		snapshot.state = 1
		snapshot.card_id = "focus"
		snapshot.phase = "windup" if float(m.phase_time)<0.5 else "recover"
		snapshot.phase_progress = clampf(float(m.phase_time)*2.0,0.0,1.0) if snapshot.phase == "windup" else clampf((float(m.phase_time)-0.5)*2.0,0.0,1.0)
		return snapshot
	if not active or beat.is_empty():
		return snapshot
	var action: Dictionary = beat.actions[role]
	var contact_at := Match.START_S+float(action.start)*Match.FRAME_S
	snapshot.action_seq += int(beat.beat)
	snapshot.frozen = m.visual_frozen()
	var reaction: Dictionary = _reactions.get(role,{})
	var damage_age := maxf(0.0,t-float(reaction.get("at",0.0)))
	if not reaction.is_empty():
		snapshot.flash = maxf(0.0,1.0-damage_age*4.0)
		var hit: Dictionary = reaction.hit
		var direction := 1.0 if hit.source == "player" else -1.0
		snapshot.canvas_shift.x += direction*24.0*maxf(0.0,1.0-damage_age/0.45)
		snapshot.canvas_tilt = direction*deg_to_rad(7.0)*maxf(0.0,1.0-damage_age/0.45)
		snapshot.stun_tilt = direction*0.65
		snapshot.stun_duration = 0.42 if hit.kind in ["counter","punish"] or int(hit.damage)>=8 else 0.30
		var outgoing_hold: bool = bool(action.card.attack) and not action.cancelled and snapshot.frozen and absf(t-contact_at)<0.001
		if int(snapshot.hp)<=0 and not outgoing_hold:
			snapshot.state = 5
			snapshot.state_time = damage_age
			return snapshot
		var armor: bool = action.id == "armored_heavy" and not action.cancelled and t<contact_at+Match.RECOVER_S
		if not outgoing_hold and not armor and damage_age<float(snapshot.stun_duration):
			snapshot.state = 3 if hit.kind == "blocked" else 2
			snapshot.state_time = damage_age
			return snapshot
	if action.cancelled and t>=Match.START_S+float(action.cancel_frame)*Match.FRAME_S:
		return snapshot
	if t>contact_at+Match.RECOVER_S and action.id not in ["guard","parry","sidestep"]:
		return snapshot
	snapshot.state = 1
	snapshot.card_id = String(action.clip)
	var pose_contact := maxf(0.18,contact_at-0.25) if action.id == "wave" else contact_at
	snapshot.phase = "windup"
	snapshot.phase_progress = clampf(t/maxf(0.001,pose_contact-0.10),0.0,1.0)
	if t>=pose_contact-0.10 and t<=pose_contact+0.001:
		snapshot.phase = "active"
		snapshot.phase_progress = clampf((t-(pose_contact-0.10))/0.10,0.0,1.0)
	elif t>pose_contact:
		snapshot.phase = "recover"
		snapshot.phase_progress = clampf((t-pose_contact)/Match.RECOVER_S,0.0,1.0)
	if action.id in ["guard","parry"] and t>=contact_at:
		snapshot.guarding = true
		snapshot.phase = "active"
		snapshot.phase_progress = 1.0
	if action.id == "sidestep" and t>=contact_at:
		snapshot.dodging = true
		snapshot.phase = "recover"
		snapshot.phase_progress = 0.40 if t<contact_at+0.50 else clampf(0.40+(t-contact_at-0.50)*2.0,0.40,1.0)
	if action.id == "feint":
		# Pull the jab back before contact instead of presenting a phantom hit.
		snapshot.phase = "windup"
		snapshot.phase_progress = 0.65*sin(clampf(t/maxf(contact_at,0.001),0.0,1.0)*PI)
	if _contact_gaps.has(role):
		var amount := maxf(0.0,_gap(m)-float(_contact_gaps[role])+24.0)
		if _contact_gaps.size() == 2:
			amount = maxf(0.0,_gap(m)-(float(_contact_gaps.player)+float(_contact_gaps.foe))*0.5)*0.5
		snapshot.canvas_shift.x += float(facing)*amount*_travel(t,contact_at)
	return snapshot

func native_visual(m,role: String) -> Dictionary:
	if library == null or not library.available():
		return {}
	var snap: Dictionary = sample(m,role)
	var clip := "idle"
	var frame := 0.0
	if int(snap.state) == 1:
		clip = String(snap.card_id)
		frame = library.phase_frame(role,clip,String(snap.phase),float(snap.phase_progress))
	elif int(snap.state) == 5:
		clip = "ko"
		frame = clampf(float(snap.state_time)/0.45,0.0,1.0)*float(library.clip_frames(role,clip)-1)
	elif int(snap.state) in [2,3]:
		clip = "block" if int(snap.state)==3 else ("hit_heavy" if float(snap.stun_duration)>0.30 else "hit_light")
		frame = clampf(float(snap.state_time)/float(snap.stun_duration),0.0,1.0)*float(library.clip_frames(role,clip)-1)
	else:
		frame = fposmod(_idle_time*60.0,float(maxi(1,library.clip_frames(role,clip)-1)))
	var pose: Dictionary = library.sample(role,clip,frame)
	if _helper != null:
		var shift: float = absf(float(snap.canvas_shift.x))
		if shift>35.0 and int(snap.state)==1:
			pose = _helper._travel_legs(role,pose,shift,0.35)
		var identity := str(["tactical",clip,snap.action_seq,snap.state])
		pose = _helper._transition_pose(role,pose,identity,bool(snap.frozen) or int(snap.state) in [2,3,5])
	return {"pose":pose,"facing":snap.facing,"canvas_shift":snap.canvas_shift,"canvas_tilt":snap.canvas_tilt,"clip_id":clip,"frame":frame,"frozen":snap.frozen}
