extends "res://scripts/hud.gd"
## Independent large decision canvas over the existing authored fighting stage.
const TDefs = preload("res://scripts/tactical_defs.gd")
const HIDDEN_MARK = preload("res://assets/tactical/hidden_card_back.png")
const CANVAS := Vector2(1600,900)
const HAND_TOP := 708.0
const HAND_HEIGHT := 172.0
const HAND_SPACE := 12.0
const INK := Color(0.95,0.96,0.99)
const SECONDARY := Color(0.77,0.82,0.90)
const SURFACE := Color(0.055,0.065,0.10,0.97)
const GOLD := Color(0.98,0.79,0.37)
const NEUTRAL := Color(0.32,0.37,0.46)
const DETAIL_WIDTH := 384.0
const PLAN_LEFT := 48.0
const PLAN_WIDTH := 1504.0
const PLAN_GAP := 10.0
const PLAN_SLOT_WIDTH := (PLAN_WIDTH-float(TDefs.PLAY-1)*PLAN_GAP)/float(TDefs.PLAY)
var hover_kind := ""
var hover_index := -1
var hover_role := "player"
var keyboard_focus_index := -1
var _last_mouse := Vector2(-1000,-1000)
var _last_phase := ""
var _display_font: SystemFont
var _regular_font: SystemFont
var _drag_from := -1
var _drag_target := -1
var _drag_start := Vector2.ZERO
var _dragging := false
var _drag_selection: Array = []
var _drag_revision := -1
var review_open := false
var review_snapshot: Dictionary = {}
var _review_focus_index := -1
var motion_enabled := OS.get_environment("CARD_BOXER_UI_MOTION") != "0"
var _selection_cue := 0.0
var _selection_key := ""

func _ready() -> void:
	super._ready()
	size = CANVAS
	# Arena scales the authored stage by 1.25; keep UI coordinates at 1600x900.
	scale = Vector2.ONE/1.25
	_regular_font = font.duplicate()
	_display_font = font.duplicate()
	_display_font.font_weight = 700

func hand_rect(index: int) -> Rect2:
	var count: int = arena.tactical.hand.size()
	if index<0 or index>=count:
		return Rect2()
	var width := minf(180.0,(1504.0-float(count-1)*HAND_SPACE)/float(count))
	var total := float(count)*width+float(count-1)*HAND_SPACE
	var lift := 8.0 if arena.tactical.selected.has(index) and arena.tactical.phase == "select" else 0.0
	return Rect2(800.0-total*0.5+float(index)*(width+HAND_SPACE),HAND_TOP-lift,width,HAND_HEIGHT)

func swap_card_rect(index: int) -> Rect2:
	var rect := hand_rect(index)
	return Rect2(rect.end-Vector2(36,33),Vector2(28,26)) if rect.has_area() else Rect2()

func hand_range_rect(index: int) -> Rect2:
	var rect := hand_rect(index)
	return Rect2(rect.position+Vector2(11,132),Vector2(82,24)) if rect.has_area() else Rect2()

func plan_rect(role: String,index: int) -> Rect2:
	if index<0 or index>=TDefs.PLAY:
		return Rect2()
	var top := 180.0 if role == "player" else 264.0
	return Rect2(PLAN_LEFT+float(index)*(PLAN_SLOT_WIDTH+PLAN_GAP),top,PLAN_SLOT_WIDTH,54.0)

func plan_card(role: String,index: int):
	var m = arena.tactical
	if index<0 or index>=TDefs.PLAY:
		return null
	if role == "player" and m.phase == "select":
		return m.hand[m.selected[index]] if index<m.selected.size() else null
	var plan: Array = m.enemy_preview if role == "foe" else m.player_plan
	return plan[index] if index<plan.size() else null

func hand_face(index: int) -> Dictionary:
	var m = arena.tactical
	if index<0 or index>=m.hand.size() or m.hand[index] == null:
		return {}
	var card: Dictionary = TDefs.card(String(m.hand[index]))
	var selected_position: int = m.selected.find(index) if m.phase == "select" else -1
	var stat := "起手%d · %d伤" % [card.windup,card.damage] if card.attack else "起手%d" % card.windup
	return {"name":String(card.name),"rank":int(card.rank),"stat":stat,"range":_range_label(card) if card.attack or int(card.get("bait_frames",0))>0 else "","range_cells":_reach_cells(card),"step":selected_position+1,"mark":_role_mark(card),"windup":int(card.windup),"damage":int(card.damage)}

func plan_face(role: String,index: int) -> Dictionary:
	var id = plan_card(role,index)
	if id == null:
		if role == "foe" and arena.tactical.phase == "select" and index<arena.tactical.enemy_preview.size():
			return {"state":"masked","slot":index+1}
		return {"state":"empty","slot":index+1}
	var card: Dictionary = TDefs.card(String(id))
	var timing := "起手%d · %d伤" % [card.windup,card.damage] if card.attack else "起手%d" % card.windup
	var stat := timing
	if card.attack or int(card.get("bait_frames",0))>0:
		stat += " · "+_range_label(card)
	var face := {"state":"visible","slot":index+1,"name":String(card.name),"rank":int(card.rank),"stat":stat,"timing":timing,"range_cells":_reach_cells(card),"kind":String(card.kind),"mark":_role_mark(card)}
	var m = arena.tactical
	if role=="player" and m.phase=="select" and m.selected.size()==TDefs.PLAY:
		if m.forecast_status=="ready" and index<m.forecast.beats.size():
			face["forecast_label"] = String(m.forecast.beats[index].label)
			face["forecast_certain"] = bool(m.forecast.beats[index].certain)
			face["status_badge"] = {"kind":"forecast","text":"预估·"+String(face.forecast_label),"certain":bool(face.forecast_certain)}
		elif m.forecast_status=="pending":
			face["forecast_label"] = "预估中"
			face["status_badge"] = {"kind":"pending","text":"预估中","certain":false}
	elif m.phase in ["resolve","round_over","match_over"]:
		var feedback: Dictionary = m.feedback_for(role,index)
		if not feedback.is_empty():
			face["result_label"] = String(feedback.label)
			face["status_badge"] = {"kind":"result","text":"实际·"+String(feedback.label),"certain":true}
	return face

func plan_content_rects(role: String,index: int) -> Dictionary:
	var rect := plan_rect(role,index)
	var face := plan_face(role,index)
	var status := Rect2()
	if face.has("status_badge"):
		var width := font.get_string_size(String(face.status_badge.text),HORIZONTAL_ALIGNMENT_LEFT,-1,17).x+12.0
		status = Rect2(rect.end.x-8.0-width,rect.position.y+4.0,width,24.0)
	var name_end := status.position.x-8.0 if status.has_area() else rect.end.x-8.0
	var reach := Rect2(rect.end.x-83.0,rect.position.y+31.0,75.0,20.0) if not face.get("range_cells",[]).is_empty() else Rect2()
	var timing_end := reach.position.x-8.0 if reach.has_area() else rect.end.x-8.0
	return {"name":Rect2(rect.position+Vector2(44,3),Vector2(name_end-rect.position.x-44.0,26)),"status":status,"timing":Rect2(rect.position+Vector2(44,30),Vector2(timing_end-rect.position.x-44.0,22)),"range":reach}

func _reach_cells(card: Dictionary) -> Array:
	if not card.attack and int(card.get("bait_frames",0))==0:
		return []
	var cells: Array = []
	for distance in range(3):
		cells.append(distance>=int(card.range_min) and distance<=int(card.range_max))
	return cells

func card_detail(id: String) -> Dictionary:
	var card: Dictionary = TDefs.card(id)
	if card.is_empty():
		return {}
	var role := _role_label(card)
	var info := role
	if int(card.combo_cost)>0:
		info += " · %d点" % card.combo_cost
	if card.attack:
		info += " · 打断%d" % card.impact
		if int(card.stun_guard)>0:
			info += " · 抗断%d" % card.stun_guard
	elif int(card.get("defense_window",0))>0:
		info += " · %d帧窗口" % card.defense_window
	var timing := "收招%d" % card.recover
	if card.attack:
		timing += " · 打空%d · 命中%+d" % [card.whiff_recover,int(card.hitstun)-int(card.recover)]
		if not card.ignore_defenses.has("block"):
			timing += " · 被防%+d" % (int(card.blockstun)-int(card.recover))
	return {"name":String(card.name),"body":String(card.text),"meta":"起手%d" % card.windup+(" · %d伤 · %s" % [card.damage,_range_label(card)] if card.attack or int(card.get("bait_frames",0))>0 else ""),"role":role,"recover":int(card.recover),"whiff_recover":int(card.whiff_recover),"info":info,"timing":timing}

func _range_label(card: Dictionary) -> String:
	return TDefs.range_label(card)

func _role_label(card: Dictionary) -> String:
	if card.attack:
		return {"starter":"连段起始","starter_linker":"连段起始 / 连接","linker":"连接","ender":"终结","standalone":"独立"}.get(card.combo_role,"攻击")
	if card.defense!="":
		return {"block":"格挡","dodge":"侧闪","parry":"招架"}.get(card.defense,"守御")
	return "骗防" if int(card.get("bait_frames",0))>0 else ("位移" if card.kind=="move" else "调整")

func _role_mark(card: Dictionary) -> String:
	if card.attack:
		return {"starter":"起","starter_linker":"连","linker":"连","ender":"终","standalone":"独"}.get(card.combo_role,"击")
	if card.defense!="":
		return {"block":"挡","dodge":"闪","parry":"架"}.get(card.defense,"守")
	return "骗" if int(card.get("bait_frames",0))>0 else _action_mark(String(card.kind))

func _action_mark(kind: String) -> String:
	return {"attack":"击","guard":"守","move":"移","power":"势"}.get(kind,"·")

func _tactical_color(kind: String) -> Color:
	return {"attack":Color(0.81,0.48,0.46),"guard":Color(0.53,0.66,0.79),"move":Color(0.55,0.72,0.65),"power":Color(0.67,0.60,0.78)}.get(kind,SECONDARY)

func offer_rect(index: int) -> Rect2:
	return Rect2(136.0+float(index%3)*448.0,270.0+float(index/3)*178.0,432.0,156.0)

func confirm_rect() -> Rect2:
	if arena.tactical.phase == "loadout":
		return Rect2(604,806,392,48)
	if arena.tactical.phase == "match_over":
		return Rect2(640,560,320,48)
	return Rect2(1384,660,168,40)

func undo_rect() -> Rect2:
	return Rect2(1252,660,120,40)

func pause_rect() -> Rect2:
	return Rect2(676,100,120,32)

func restart_rect() -> Rect2:
	return Rect2(804,100,120,32)

func review_rect() -> Rect2:
	return Rect2(780,660,120,40)

func review_panel_rect() -> Rect2:
	return Rect2(136,164,1328,652)

func review_close_rect() -> Rect2:
	return Rect2(1296,180,144,40)

func review_available() -> bool:
	return arena.tactical.phase=="select" and not arena.tactical.last_exchange_feedback.is_empty()

func close_review(restore_focus: bool = true) -> void:
	if review_open and restore_focus:
		keyboard_focus_index = _review_focus_index
	review_open = false
	review_snapshot.clear()
	_review_focus_index = -1
	_clear_drag()

func toggle_review() -> bool:
	if review_open:
		close_review()
	elif review_available():
		_review_focus_index = keyboard_focus_index
		review_snapshot = arena.tactical.last_exchange_details()
		review_open = true
		_clear_drag()
		hover_kind = ""
		hover_index = -1
		_selection_cue = 0.0
	else:
		return false
	_changed()
	return true

func handle_key_event(event: InputEventKey) -> bool:
	if event.keycode==KEY_R:
		close_review(false)
		return false
	if event.keycode==KEY_H:
		toggle_review()
		return true
	if review_open:
		if event.keycode==KEY_ESCAPE:
			close_review()
			_changed()
		return event.keycode!=KEY_P
	return false

func _joker_rect(role: String,index: int) -> Rect2:
	return Rect2((48.0 if role == "player" else 940.0)+float(index)*208.0,100.0,196.0,32.0)

func focus_card(index: int) -> void:
	keyboard_focus_index = index

func _changed() -> void:
	arena._mirror_tactical()
	arena.force_redraw()

func _clear_drag() -> void:
	_drag_from = -1
	_drag_target = -1
	_dragging = false
	_drag_selection = []
	_drag_revision = -1

func _valid_drag() -> bool:
	var m = arena.tactical
	return m.phase=="select" and not m.paused and not m.bot and m.selected==_drag_selection and int(m.plan_revision)==_drag_revision

func _drop_slot(at: Vector2) -> int:
	for index in range(TDefs.PLAY):
		if plan_rect("player",index).has_point(at):
			return index
	return -1

func handle_mouse_event(event: InputEvent) -> bool:
	var m = arena.tactical
	if review_open:
		if event is InputEventMouseButton and event.pressed and event.button_index==MOUSE_BUTTON_LEFT:
			handle_click(event.position)
		return true
	if event is InputEventMouseMotion:
		if _drag_from<0:
			return false
		if not _valid_drag() or (event.button_mask&MOUSE_BUTTON_MASK_LEFT)==0:
			_clear_drag()
			_changed()
			return true
		_dragging = _dragging or event.position.distance_to(_drag_start)>=6.0
		_drag_target = _drop_slot(event.position)
		arena.force_redraw()
		return true
	if not event is InputEventMouseButton or event.button_index!=MOUSE_BUTTON_LEFT:
		return false
	if event.pressed:
		_clear_drag()
		if m.phase=="select" and not m.paused and not m.bot:
			for index in range(m.selected.size()):
				if plan_rect("player",index).has_point(event.position):
					_drag_from = index
					_drag_start = event.position
					_drag_selection = m.selected.duplicate()
					_drag_revision = int(m.plan_revision)
					return true
		return handle_click(event.position)
	if _drag_from<0:
		return false
	var from := _drag_from
	var drag: bool = _dragging or event.position.distance_to(_drag_start)>=6.0
	var valid := _valid_drag()
	var to := _drop_slot(event.position)
	_clear_drag()
	if valid:
		if drag and to>=0:
			m.move_selected(from,mini(to,m.selected.size()-1))
		elif not drag:
			m.toggle(m.selected[from])
	_changed()
	return true

func handle_click(at: Vector2) -> bool:
	var m = arena.tactical
	if restart_rect().has_point(at) or (m.phase == "match_over" and confirm_rect().has_point(at)):
		close_review(false)
		arena._start_tactical_match()
		return true
	if pause_rect().has_point(at):
		arena.paused = not arena.paused
		m.paused = arena.paused
		_changed()
		return true
	if review_open:
		if review_close_rect().has_point(at) or review_rect().has_point(at):
			close_review()
			_changed()
		return true
	if review_available() and review_rect().has_point(at):
		return toggle_review()
	if m.paused or m.bot:
		return false
	if m.phase == "select" and undo_rect().has_point(at):
		m.undo()
		_changed()
		return true
	if confirm_rect().has_point(at):
		var changed: bool = m.confirm()
		keyboard_focus_index = -1
		_changed()
		return changed
	if m.phase == "loadout":
		for index in range(m.offers.size()):
			if offer_rect(index).has_point(at):
				m.toggle(index)
				_changed()
				return true
	elif m.phase == "select":
		for index in range(m.selected.size()):
			if plan_rect("player",index).has_point(at):
				m.toggle(m.selected[index])
				_changed()
				return true
		for index in range(m.hand.size()):
			if swap_card_rect(index).has_point(at):
				var changed: bool = m.swap_card(index)
				keyboard_focus_index = -1
				_changed()
				return changed
			if hand_rect(index).has_point(at):
				m.toggle(index)
				_changed()
				return true
	return false

func _process(delta: float) -> void:
	if arena == null or arena.tactical == null:
		return
	var m = arena.tactical
	if review_open and not review_available():
		close_review(false)
	if _drag_from>=0 and not _valid_drag():
		_clear_drag()
	var selection_key := str([m.phase,m.selected,m.plan_revision])
	if selection_key!=_selection_key:
		_selection_cue = 1.0 if motion_enabled and m.phase=="select" and _selection_key!="" else 0.0
		_selection_key = selection_key
	_selection_cue = maxf(0.0,_selection_cue-delta/0.16) if motion_enabled else 0.0
	var mouse := get_global_mouse_position()
	if mouse.distance_to(_last_mouse)>1.0 or m.phase != _last_phase:
		keyboard_focus_index = -1
	_last_mouse = mouse
	_last_phase = m.phase
	hover_kind = ""
	hover_index = -1
	hover_role = "player"
	if review_open:
		super._process(delta)
		return
	if m.phase == "loadout":
		for i in range(m.offers.size()):
			if offer_rect(i).has_point(mouse):
				hover_kind = "offer"
				hover_index = i
	else:
		for i in range(m.hand.size()):
			if m.hand[i] != null and hand_rect(i).has_point(mouse):
				hover_kind = "card"
				hover_index = i
				if m.phase=="select" and swap_card_rect(i).has_point(mouse):
					hover_kind = "swap"
		for role in ["player","foe"]:
			for i in range(TDefs.PLAY):
				if plan_rect(role,i).has_point(mouse):
					hover_kind = "plan"
					hover_index = i
					hover_role = role
			for i in range(m.state[role].jokers.size()):
				if _joker_rect(role,i).has_point(mouse):
					hover_kind = "joker"
					hover_index = i
					hover_role = role
	if keyboard_focus_index>=0:
		hover_kind = "offer" if m.phase == "loadout" else "card"
		hover_index = keyboard_focus_index
		hover_role = "player"
	super._process(delta)

func _visual_key() -> String:
	return super._visual_key()+str([hover_kind,hover_index,hover_role,keyboard_focus_index,_drag_from,_drag_target,_dragging,review_open,review_snapshot,int(ceil(_selection_cue*8.0))])+(arena.tactical.signature() if arena != null and arena.tactical != null else "")

func _face(size_value: int) -> Font:
	return _display_font if size_value>=20 and _display_font != null else font

func _text(value: String,at: Vector2,size_value: int = 17,color: Color = INK) -> void:
	draw_string(_face(size_value),at,value,HORIZONTAL_ALIGNMENT_LEFT,-1,size_value,color)

func _center(value: String,rect: Rect2,size_value: int = 17,color: Color = INK) -> void:
	var width := _face(size_value).get_string_size(value,HORIZONTAL_ALIGNMENT_LEFT,-1,size_value).x
	_text(value,Vector2(rect.get_center().x-width*0.5,rect.get_center().y+float(size_value)*0.35),size_value,color)

func _wrap_pixels(value: String,width: float,size_value: int) -> Array:
	var lines: Array = []
	var line := ""
	for i in range(value.length()):
		var character := value.substr(i,1)
		if character == "\n":
			lines.append(line)
			line = ""
		elif line != "" and _face(size_value).get_string_size(line+character,HORIZONTAL_ALIGNMENT_LEFT,-1,size_value).x>width and not NO_LINE_START.contains(character):
			lines.append(line)
			line = character
		else:
			line += character
	if line != "":
		lines.append(line)
	return lines

func _ellipsize(value: String,width: float,size_value: int) -> String:
	while _face(size_value).get_string_size(value+"…",HORIZONTAL_ALIGNMENT_LEFT,-1,size_value).x>width and value.length()>0:
		value = value.left(value.length()-1)
	return value+"…"

func _button(rect: Rect2,label: String,enabled: bool = true,primary: bool = true) -> void:
	var hovered := enabled and rect.has_point(_last_mouse)
	draw_rect(rect,GOLD if enabled and primary else (Color(0.15,0.18,0.24,0.98) if hovered else Color(0.10,0.12,0.17,0.98)))
	draw_rect(rect,GOLD if enabled and primary else (SECONDARY if hovered else NEUTRAL),false,1.0)
	_center(label,rect,18,Color(0.09,0.08,0.06) if enabled and primary else (INK if enabled else SECONDARY))

func _draw_reach(cells: Array,rect: Rect2,accent: Color) -> void:
	if cells.is_empty():
		return
	var width := (rect.size.x-6.0)/3.0
	for index in range(3):
		var cell := Rect2(rect.position+Vector2(float(index)*(width+3.0),0),Vector2(width,rect.size.y))
		draw_rect(cell,Color(0.15,0.18,0.23) if cells[index] else Color(0.06,0.075,0.11))
		draw_rect(cell,accent if cells[index] else NEUTRAL,false,1.0)
		if cells[index]:
			draw_line(cell.position+Vector2(1,cell.size.y-1),cell.end-Vector2(1,1),accent,2.0)
		_center(["贴","中","远"][index],cell,17,INK if cells[index] else SECONDARY)

func _draw_dashed_rect(rect: Rect2,color: Color) -> void:
	for edge in [[rect.position,Vector2(rect.end.x,rect.position.y)],[Vector2(rect.end.x,rect.position.y),rect.end],[rect.end,Vector2(rect.position.x,rect.end.y)],[Vector2(rect.position.x,rect.end.y),rect.position]]:
		var start: Vector2 = edge[0]
		var end: Vector2 = edge[1]
		var length := start.distance_to(end)
		var direction := start.direction_to(end)
		var at := 0.0
		while at<length:
			draw_line(start+direction*at,start+direction*minf(at+4.0,length),color,1.0)
			at += 7.0

func _draw_status_badge(badge: Dictionary,rect: Rect2) -> void:
	draw_rect(rect,Color(0.11,0.14,0.19))
	if badge.kind=="forecast" and not badge.certain:
		_draw_dashed_rect(rect,SECONDARY)
	else:
		draw_rect(rect,SECONDARY if badge.kind=="result" else Color(0.43,0.53,0.64),false,1.0)
	_center(String(badge.text),rect,17,INK if badge.kind=="result" else SECONDARY)

func _draw() -> void:
	if arena == null or arena.tactical == null or font == null:
		return
	var started := Time.get_ticks_usec()
	arena.redraw_stats.hud_draws += 1
	_draw_header()
	if arena.tactical.phase == "loadout":
		_draw_loadout()
	else:
		_draw_plans()
		_draw_tactical_hand()
		_draw_sources()
		_draw_actor_status()
		_draw_tooltip()
		if arena.tactical.phase == "match_over":
			_draw_match_end()
	_draw_footer()
	if arena.paused:
		draw_rect(Rect2(0,136,1600,764),Color(0.01,0.02,0.04,0.66))
		if not review_open:
			_center("已暂停 · P 或上方按钮继续",Rect2(480,400,640,74),30,GOLD)
	if review_open:
		_draw_review()
	else:
		draw_set_transform(Vector2.ZERO,0.0,Vector2(1.25,1.25))
		_draw_profile()
		draw_set_transform(Vector2.ZERO)
	arena.redraw_stats.hud_draw_us += Time.get_ticks_usec()-started

func _draw_header() -> void:
	var m = arena.tactical
	draw_rect(Rect2(0,0,1600,136),Color(0.035,0.045,0.075,0.96))
	_draw_bar_v2(Vector2(112,40),arena.player.hp_ratio(),float(_hp_shown.p),false,"你",true)
	_draw_bar_v2(Vector2(1036,40),arena.enemy.hp_ratio(),float(_hp_shown.e),true,"青岚",false)
	_draw_rage_bar(Vector2(112,70),float(m.state.player.rage)/100.0,false)
	_draw_rage_bar(Vector2(1036,70),float(m.state.foe.rage)/100.0,true)
	_text("怒火 %d%%" % int(m.state.player.rage)+(" · EX准备" if float(m.state.player.rage)>=100.0 else ""),Vector2(112,94),17,SECONDARY)
	var rage_label := "怒火 %d%%" % int(m.state.foe.rage)+(" · EX准备" if float(m.state.foe.rage)>=100.0 else "")
	_text(rage_label,Vector2(1488-font.get_string_size(rage_label,HORIZONTAL_ALIGNMENT_LEFT,-1,17).x,94),17,SECONDARY)
	_center("第 %d 局 · 第 %d 轮 / %d" % [m.round_index,m.turn_index,TDefs.TURNS],Rect2(660,8,280,26),17,SECONDARY)
	_center("%d : %d" % [m.wins[0],m.wins[1]],Rect2(704,36,192,42),34,INK)
	_button(pause_rect(),"继续 P" if arena.paused else "暂停 P",true,false)
	_button(restart_rect(),"重开 R",true,false)
	if portrait_ui_enabled:
		draw_texture_rect(TEX_AVATAR_P,Rect2(48,24,52,52),false)
		draw_texture_rect(TEX_AVATAR_E,Rect2(1500,24,52,52),false)
	for role in ["player","foe"]:
		for index in range(TDefs.JOKER_SLOTS):
			var rect := _joker_rect(role,index)
			draw_rect(rect,SURFACE)
			if index<m.state[role].jokers.size():
				var id: String = m.state[role].jokers[index]
				var joker: Dictionary = TDefs.joker(id)
				var triggered := ""
				if m.phase == "resolve":
					for hit in m.latest_hits:
						if hit.source == role:
							for part in hit.parts:
								if part.name == joker.name:
									triggered = String(part.op)+("%.2f" % float(part.value) if part.op=="×" else str(int(part.value)))
						for trigger in hit.get("triggers",[]):
							if trigger.role == role and trigger.id == id:
								triggered = "触发"
				draw_rect(rect,GOLD if triggered != "" else NEUTRAL,false,2.0 if triggered != "" else 1.0)
				_text(str(index+1),rect.position+Vector2(12,23),17,SECONDARY)
				_text(String(joker.name),rect.position+Vector2(34,23),18,INK)
				if triggered != "":
					_text(triggered,Vector2(rect.end.x-12-font.get_string_size(triggered,HORIZONTAL_ALIGNMENT_LEFT,-1,17).x,rect.position.y+23),17,GOLD)
			else:
				draw_rect(rect,Color(0.28,0.33,0.41),false,1.0)
				_center("待选天赋",rect,16,SECONDARY)

func _draw_loadout() -> void:
	var m = arena.tactical
	draw_rect(Rect2(100,174,1400,700),SURFACE)
	draw_rect(Rect2(100,174,1400,700),NEUTRAL,false,1.0)
	_text("选择战术天赋",Vector2(136,224),32,INK)
	_text("六选三 · 按所选顺序触发",Vector2(136,253),18,SECONDARY)
	for index in range(m.offers.size()):
		var rect := offer_rect(index)
		var joker: Dictionary = TDefs.joker(m.offers[index])
		var picked: bool = m.selected.has(index)
		draw_rect(rect,Color(0.13,0.12,0.10) if picked else Color(0.08,0.095,0.14))
		draw_rect(rect,GOLD if picked else (SECONDARY if hover_kind=="offer" and hover_index==index else NEUTRAL),false,2.0 if picked else 1.0)
		_text(String(joker.name),rect.position+Vector2(22,38),27,INK)
		_text("第 %d 位" % (m.selected.find(index)+1) if picked else "按键 %d" % (index+1),rect.position+Vector2(rect.size.x-96,36),16,GOLD if picked else SECONDARY)
		var summary := _wrap_pixels(joker_summary(String(m.offers[index])),rect.size.x-44,18)
		for line in range(summary.size()):
			_text(summary[line],rect.position+Vector2(22,72+float(line)*22),18,INK)
		var body_top := 100.0+float(maxi(0,summary.size()-1))*22.0
		var lines: Array = _wrap_pixels(String(joker.text),rect.size.x-44,16)
		for line in range(lines.size()):
			_text(lines[line],rect.position+Vector2(22,body_top+float(line)*21),16,SECONDARY)
	for index in range(TDefs.JOKER_SLOTS):
		var rect := Rect2(136+float(index)*448,656,432,58)
		draw_rect(rect,Color(0.08,0.085,0.12))
		draw_rect(rect,GOLD if index<m.selected.size() else NEUTRAL,false,1.0)
		var label := "%d · " % (index+1)+(String(TDefs.joker(m.offers[m.selected[index]]).name) if index<m.selected.size() else "选择天赋")
		_center(label,rect,22,GOLD if index<m.selected.size() else SECONDARY)
		if index<TDefs.JOKER_SLOTS-1:
			draw_line(Vector2(rect.end.x+3,rect.get_center().y),Vector2(rect.end.x+13,rect.get_center().y),SECONDARY,1.0)
	var help := "选好后从八张手牌编排五招，敌方明三暗二。"
	if hover_kind=="offer" and hover_index>=0 and hover_index<m.offers.size():
		var joker: Dictionary = TDefs.joker(m.offers[hover_index])
		help = String(joker.name)+"："+String(joker.text)
	_text(help,Vector2(136,760),18,SECONDARY)
	_button(confirm_rect(),"确认天赋 · 空格" if m.selected.size()==TDefs.JOKER_SLOTS else "还需选 %d 项" % (TDefs.JOKER_SLOTS-m.selected.size()),m.selected.size()==TDefs.JOKER_SLOTS)

func joker_summary(id: String) -> String:
	return {
		"shadow":"闪避成功 → 下次攻击 +3",
		"opening":"确反 → 伤害 ×1.25",
		"counter":"打康 → 伤害 +3",
		"pressure":"首次打康 → 下一拍攻击起手 -2",
		"wind":"首次闪避 / 招架 → 下轮多摸1",
		"sequence":"三连 / 五连 → 攻击 ×1.25",
		"triple":"三同 / 葫芦 / 四同 / 五同 → 攻击 +2",
		"breaker":"首次投技 / 破防命中 → 下轮多摸1"
	}.get(id,"")

func _draw_plans() -> void:
	draw_rect(Rect2(0,136,1600,182),Color(0.035,0.045,0.075,0.84))
	_draw_plan_row("player")
	_draw_plan_row("foe")

func _draw_plan_row(role: String) -> void:
	var m = arena.tactical
	var player_side: bool = role == "player"
	var header_y := 165.0 if player_side else 250.0
	var label := "你 · %s" % TDefs.distance_label(int(m.state.distance)) if player_side else "青岚 · %d明 %d暗" % [TDefs.PLAY-TDefs.ENEMY_HIDDEN,TDefs.ENEMY_HIDDEN] if m.phase == "select" else "青岚"
	if player_side and int(m.state.player.ready_delay)>0:
		label += " · 后手%d" % m.state.player.ready_delay
	if player_side and m.phase=="resolve" and not m.active_beat.is_empty():
		var used := int(m.active_beat.actions.player.combo_used) if m.active_beat.actions.player.combo_applied else int(m.state.player.combo.used)
		label += " · 连段%d/%d" % [used,TDefs.COMBO_BUDGET]
	_text(label,Vector2(PLAN_LEFT,header_y),18,INK)
	if player_side and m.phase=="select" and m.selected.size()==TDefs.PLAY:
		_text("预估暂不可用 · 可正常开打" if m.forecast_status=="error" else "公开预估",Vector2(340,header_y),17,SECONDARY)
	elif not player_side and hover_kind=="plan":
		_text("同拍对照 · 第%d拍" % (hover_index+1),Vector2(340,header_y),17,SECONDARY)
	var plan: Array = []
	var hidden_count := 0
	for index in range(TDefs.PLAY):
		var face: Dictionary = plan_face(role,index)
		var slot := int(face.slot)
		plan.append(plan_card(role,index))
		if face.state == "masked":
			hidden_count += 1
		var rect := plan_rect(role,index)
		var active: bool = m.phase == "resolve" and not m.active_beat.is_empty() and int(m.active_beat.beat)==index+1
		var card_color: Color = _tactical_color(String(face.get("kind","attack"))) if face.state == "visible" else Color(0.37,0.42,0.51)
		var outline: Color = GOLD if active else (card_color if face.state == "visible" else Color(0.32,0.36,0.44))
		var paired_hover := hover_kind=="plan" and hover_index==index
		if paired_hover and not active:
			outline = SECONDARY
		if player_side and _dragging and index in [_drag_from,_drag_target]:
			outline = GOLD
		draw_rect(rect,SURFACE)
		if face.state == "visible":
			draw_rect(Rect2(rect.position,Vector2(1.0,rect.size.y)),outline)
		elif face.state == "masked":
			draw_texture_rect(HIDDEN_MARK,rect,false,Color(0.72,0.73,0.82,0.25))
		draw_rect(rect,outline,false,2.0 if active or paired_hover else 1.0)
		var badge := Rect2(rect.position+Vector2(8,14),Vector2(28,26))
		draw_rect(badge,Color(card_color.r,card_color.g,card_color.b,0.20))
		_center("%02d" % slot,badge,17,GOLD if active else SECONDARY)
		if face.state == "visible":
			var regions := plan_content_rects(role,index)
			_text(String(face.name),regions.name.position+Vector2(0,20),20,INK)
			_text(String(face.timing),regions.timing.position+Vector2(0,17),18,SECONDARY)
			_draw_reach(face.range_cells,regions.range,card_color)
			if face.has("status_badge"):
				_draw_status_badge(face.status_badge,regions.status)
		elif face.state == "masked":
			_center("?",Rect2(rect.position+Vector2(rect.size.x*0.5-18,0),Vector2(36,54)),36,INK)
		else:
			_center("待编排",Rect2(rect.position+Vector2(44,0),Vector2(rect.size.x-52,54)),18,SECONDARY)
	if hidden_count == 0 and plan.size() == TDefs.PLAY:
		var complete := true
		for id in plan:
			complete = complete and id != null
		if complete:
			var pattern: Dictionary = m.patterns.get(role,TDefs.evaluate(plan)) if m.phase != "select" else TDefs.evaluate(plan)
			var label_pattern := "%s  +%d  ×%.2f" % [pattern.name,pattern.flat,pattern.mult]
			var x := 1552.0-_regular_font.get_string_size(label_pattern,HORIZONTAL_ALIGNMENT_LEFT,-1,18).x
			_text(label_pattern,Vector2(x,header_y),18,GOLD)


func _draw_tactical_hand() -> void:
	var m = arena.tactical
	draw_rect(Rect2(0,656,1600,244),Color(0.035,0.045,0.07,0.94))
	draw_line(Vector2(48,657),Vector2(1552,657),Color(0.36,0.39,0.48,0.70),1.0)
	var hand_title := "手牌  %d" % m.hand.filter(func(id): return id != null).size()
	_text(hand_title,Vector2(48,686),20,INK)
	var selected_label := "已编排 %d / %d" % [m.selected.size(),TDefs.PLAY] if m.phase == "select" else ""
	_text(selected_label,Vector2(178,685),18,GOLD)
	if m.phase == "select":
		var recap: Dictionary = m.last_exchange_details()
		if not recap.is_empty():
			_text("上轮：造成%d / 受伤%d" % [recap.dealt,recap.taken],Vector2(340,685),18,SECONDARY)
			_button(review_rect(),"回顾 H",true,false)
		else:
			_text("先读对手，再编排五招",Vector2(340,685),17,SECONDARY)
		var change_label := "换牌剩余 %d / %d" % [TDefs.DISCARD_MAX-m.swaps_used,TDefs.DISCARD_MAX]
		_text(change_label,Vector2(1006,685),18,SECONDARY)
		_button(undo_rect(),"撤回" if not m.selected.is_empty() else "已撤空",not m.selected.is_empty(),false)
		var enabled: bool = m.selected.size()==TDefs.PLAY
		_button(confirm_rect(),"开打" if enabled else "还需 %d 张" % (TDefs.PLAY-m.selected.size()),enabled)
	for index in range(m.hand.size()):
		var rect := hand_rect(index)
		if m.hand[index] == null:
			draw_rect(rect,Color(0.035,0.045,0.07,0.8))
			draw_rect(rect,Color(0.24,0.29,0.37),false,1.0)
			_center("—",rect,25,SECONDARY)
			continue
		var face := hand_face(index)
		var accent := _tactical_color(String(TDefs.card(String(m.hand[index])).kind))
		var picked: bool = int(face.step)>0
		draw_rect(rect,Color(0.042,0.048,0.069,0.98))
		draw_rect(Rect2(rect.position,Vector2(1.0,rect.size.y)),accent)
		if picked:
			draw_rect(rect,GOLD.lerp(INK,_selection_cue*0.3),false,1.5)
		elif hover_index==index and hover_kind in ["card","swap"]:
			draw_rect(rect,SECONDARY,false,1.0)
		if picked:
			var number: String = "%02d" % int(face.step)
			var badge := Rect2(rect.position+Vector2(10,10),Vector2(31,25))
			draw_rect(badge,Color(GOLD.r,GOLD.g,GOLD.b,0.18))
			_center(number,badge,17,GOLD)
		else:
			var mark_box := Rect2(rect.position+Vector2(10,10),Vector2(26,24))
			draw_rect(mark_box,Color(accent.r,accent.g,accent.b,0.15))
			_center(String(face.mark),mark_box,17,accent)
		_text(str(face.rank),rect.position+Vector2(rect.size.x-29,30),24,SECONDARY)
		_text(String(face.name),rect.position+Vector2(11,69),22,INK)
		var stat_rect := Rect2(rect.position+Vector2(11,88),Vector2(rect.size.x-22,25))
		_text(String(face.stat),stat_rect.position+Vector2(0,18),18,SECONDARY)
		draw_line(rect.position+Vector2(11,123),rect.end+Vector2(-11,-49),Color(accent.r,accent.g,accent.b,0.32),1.0)
		if not face.range_cells.is_empty():
			_draw_reach(face.range_cells,hand_range_rect(index),accent)
		else:
			_text({"guard":"防御","move":"位移","power":"调整"}.get(String(TDefs.card(String(m.hand[index])).kind)),rect.position+Vector2(11,150),17,SECONDARY)
		if m.phase == "select":
			var enabled: bool = m.swaps_used<TDefs.DISCARD_MAX
			var button := swap_card_rect(index)
			draw_rect(button,Color(0.07,0.08,0.11,0.96))
			draw_rect(button,SECONDARY if enabled and hover_kind=="swap" and hover_index==index else NEUTRAL,false,1.0)
			_center("换" if enabled else "满",button,17,INK if enabled else SECONDARY)

func _draw_actor_status() -> void:
	var m = arena.tactical
	for role in ["player","foe"]:
		var fighter = arena.player if role == "player" else arena.enemy
		var labels: Array = []
		if int(m.state[role].ready_delay)>0:
			labels.append("后手%d帧" % m.state[role].ready_delay)
		if m.state[role].focus:
			labels.append("蓄势 +3")
		if m.phase=="resolve" and m.state[role].combo.open:
			labels.append("连段%d/%d" % [m.state[role].combo.used,TDefs.COMBO_BUDGET])
		if not labels.is_empty():
			var rect := Rect2(fighter.global_position.x-132,474,264,28)
			draw_rect(rect,SURFACE)
			_center(" / ".join(PackedStringArray(labels)),rect,17,GOLD)

func source_feedback(role: String) -> Dictionary:
	var m = arena.tactical
	if m.phase!="resolve" or m.active_beat.is_empty() or review_open:
		return {}
	var tooltip := tooltip_detail()
	if not tooltip.is_empty() and tooltip.role==role and not _dragging:
		return {}
	return m.feedback_for(role,int(m.active_beat.beat)-1)

func _feedback_body(feedback: Dictionary) -> String:
	if String(feedback.reason)!="":
		return String(feedback.reason)
	var pieces: Array = []
	for part in feedback.parts:
		pieces.append(String(part.name)+(str(int(part.value)) if part.op=="base" else String(part.op)+("%.2f" % float(part.value) if part.op=="×" else str(int(part.value)))))
	return " → ".join(PackedStringArray(pieces)) if not pieces.is_empty() else "招式已完成"

func _draw_sources() -> void:
	for role in ["player","foe"]:
		var feedback := source_feedback(role)
		if feedback.is_empty() or feedback.kind=="setup":
			continue
		var left := 48.0 if role == "player" else 1552.0-DETAIL_WIDTH
		var lines := _wrap_pixels(_feedback_body(feedback),DETAIL_WIDTH-32.0,18)
		var height := 58.0+float(lines.size())*24.0
		var top := 640.0-height
		draw_rect(Rect2(left,top,DETAIL_WIDTH,height),SURFACE)
		var title: String = feedback.label
		if int(feedback.damage)>0:
			title += " · %d伤害" % int(feedback.damage)
		elif int(feedback.taken)>0:
			title += " · 受伤%d" % int(feedback.taken)
		_text(title,Vector2(left+16,top+34),22,GOLD)
		for i in range(lines.size()):
			_text(lines[i],Vector2(left+16,top+62+float(i)*24),18,SECONDARY)

func tooltip_detail() -> Dictionary:
	var m = arena.tactical
	var title := ""
	var body := ""
	var sections: Array = []
	var role := hover_role if hover_kind in ["plan","joker"] else "player"
	var id = null
	if hover_kind == "card" and hover_index>=0 and hover_index<m.hand.size():
		id = m.hand[hover_index]
	elif hover_kind == "swap":
		title = "换一张牌" if m.swaps_used<TDefs.DISCARD_MAX else "本轮换牌已用完"
		body = "本轮还可换%d次；换掉已编排的牌，只撤回这一张。" % (TDefs.DISCARD_MAX-m.swaps_used) if m.swaps_used<TDefs.DISCARD_MAX else "下一轮恢复换牌次数；仍可正常编排和开打。"
	elif hover_kind == "plan":
		id = plan_card(hover_role,hover_index)
		if id == null and hover_role == "foe" and m.phase == "select":
			title = "暗牌 · 第%d拍" % (hover_index+1)
			body = "对手已锁定，开打时揭晓。"
	if id != null:
		var detail: Dictionary = card_detail(String(id))
		title = String(detail.name)
		body = String(detail.body)
		sections.append({"text":String(detail.meta),"color":GOLD,"size":18})
		sections.append({"text":String(detail.info),"color":SECONDARY,"size":18})
		sections.append({"text":String(detail.timing),"color":SECONDARY,"size":18})
		if hover_kind=="plan" and hover_role=="player" and m.phase=="select" and m.forecast_status=="ready" and hover_index<m.forecast.beats.size():
			var row: Dictionary = m.forecast.beats[hover_index]
			var prediction := "预估·未执行" if row.kinds==["skipped"] else "预估 %d–%d伤 · 实际起手 %d–%d帧" % [row.damage_min,row.damage_max,row.start_min,row.start_max]
			sections.append({"text":prediction,"color":GOLD,"size":18})
			if row.kinds!=["skipped"]:
				sections.append({"text":"反击窗口 %d–%d帧" % [row.window_min,row.window_max],"color":SECONDARY,"size":18})
			sections.append({"text":"结果类别一致；伤害以范围为准。" if row.certain else "受暗牌或前拍影响，结果可能变化。","color":SECONDARY,"size":17})
		elif hover_kind=="plan" and m.phase in ["resolve","round_over","match_over"]:
			var feedback: Dictionary = m.feedback_for(role,hover_index)
			if not feedback.is_empty():
				sections.append({"text":"实际·"+String(feedback.label)+" · "+_feedback_body(feedback),"color":GOLD,"size":18})
	elif hover_kind == "joker" and hover_index>=0 and hover_index<m.state[hover_role].jokers.size():
		var joker: Dictionary = TDefs.joker(m.state[hover_role].jokers[hover_index])
		title = joker.name
		body = joker.text
		sections.append({"text":"第%d位 · 按所选顺序触发" % (hover_index+1),"color":GOLD,"size":18})
	if title == "":
		return {}
	sections.append({"text":body,"color":SECONDARY,"size":18})
	return {"title":title,"body":body,"role":role,"sections":sections}

func _tooltip_height(detail: Dictionary) -> float:
	var height := 56.0
	for section in detail.sections:
		height += float(_wrap_pixels(section.text,DETAIL_WIDTH-32.0,section.size).size())*22.0+4.0
	return height

func _draw_tooltip() -> void:
	if _dragging or review_open:
		return
	var detail := tooltip_detail()
	if detail.is_empty():
		return
	var height := _tooltip_height(detail)
	var rect := Rect2(48.0 if detail.role=="player" else 1552.0-DETAIL_WIDTH,650.0-height,DETAIL_WIDTH,height)
	draw_rect(rect,SURFACE)
	draw_rect(rect,NEUTRAL,false,1.0)
	_text(detail.title,rect.position+Vector2(16,34),24,INK)
	var cursor := 62.0
	for section in detail.sections:
		for line in _wrap_pixels(section.text,DETAIL_WIDTH-32.0,section.size):
			_text(line,rect.position+Vector2(16,cursor),section.size,section.color)
			cursor += 22.0
		cursor += 4.0

func _draw_review() -> void:
	draw_rect(Rect2(0,136,1600,764),Color(0.015,0.025,0.045,0.88))
	var panel := review_panel_rect()
	draw_rect(panel,Color(0.055,0.07,0.10))
	draw_rect(panel,NEUTRAL,false,1.0)
	_text("第%d局 · 第%d轮回顾" % [review_snapshot.round,review_snapshot.turn],panel.position+Vector2(24,38),28,INK)
	_text("造成 %d / 受伤 %d" % [review_snapshot.dealt,review_snapshot.taken],panel.position+Vector2(24,70),20,SECONDARY)
	_button(review_close_rect(),"关闭 Esc",true,false)
	_text("你",Vector2(176,253),20,INK)
	_text("青岚",Vector2(832,253),20,INK)
	for index in range(TDefs.PLAY):
		for role in ["player","foe"]:
			var rect := Rect2(160.0 if role=="player" else 816.0,270.0+float(index)*98.0,624,88)
			var feedback: Dictionary = review_snapshot.feedback[role][index]
			draw_rect(rect,Color(0.08,0.10,0.14))
			var title := "%02d · " % (index+1)
			var plan: Array = review_snapshot.get("plans",{}).get(role,[])
			if index<plan.size():
				title += String(TDefs.card(String(plan[index])).name)+" · "
			title += String(feedback.label)
			if int(feedback.damage)>0:
				title += " · %d伤害" % int(feedback.damage)
			elif int(feedback.taken)>0:
				title += " · 受伤%d" % int(feedback.taken)
			_text(title,rect.position+Vector2(16,28),20,INK)
			var lines := _wrap_pixels(_feedback_body(feedback),rect.size.x-32.0,18)
			for line in range(lines.size()):
				_text(lines[line],rect.position+Vector2(16,54+float(line)*22),18,SECONDARY)
	_text("H / Esc 关闭 · 当前编排保持不变",panel.position+Vector2(24,panel.size.y-20),17,SECONDARY)

func _draw_match_end() -> void:
	var m = arena.tactical
	draw_rect(Rect2(550,384,500,238),SURFACE)
	draw_rect(Rect2(550,384,500,238),GOLD,false,1.0)
	_center(String(m.notice),Rect2(570,408,460,58),34,GOLD)
	_center("战绩 %d : %d" % [m.wins[0],m.wins[1]],Rect2(570,485,460,32),22,SECONDARY)
	_button(confirm_rect(),"重新构筑 · R")

func _draw_footer() -> void:
	var m = arena.tactical
	var left := "1–9/0 选牌   拖动换序   Shift+数字 换牌   Backspace 撤回   空格/Enter 开打   H 回顾   P/R"
	if m.phase == "loadout":
		left = "1–6 选择天赋   Backspace 撤回"
	_text(left,Vector2(48,896),16,SECONDARY)
	var counts: Dictionary = m.deck_counts("player")
	var right := "牌堆 %d · 弃牌 %d" % [counts.draw,counts.discard]
	_text(right,Vector2(1552-font.get_string_size(right,HORIZONTAL_ALIGNMENT_LEFT,-1,16).x,896),16,SECONDARY)
