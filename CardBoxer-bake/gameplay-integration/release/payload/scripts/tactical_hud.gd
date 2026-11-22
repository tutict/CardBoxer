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
	return Rect2(rect.end-Vector2(50,32),Vector2(40,24)) if rect.has_area() else Rect2()

func plan_rect(role: String,index: int) -> Rect2:
	if index<0 or index>=TDefs.PLAY:
		return Rect2()
	var top := 219.0 if role == "player" else 312.0
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
	var stat := "%s · %d伤" % [card.speed_label,card.damage] if card.attack else "%s · %d帧" % [card.speed_label,card.windup]
	return {"name":String(card.name),"rank":int(card.rank),"stat":stat,"step":selected_position+1,"mark":_action_mark(String(card.kind))}

func plan_face(role: String,index: int) -> Dictionary:
	var id = plan_card(role,index)
	if id == null:
		if role == "foe" and arena.tactical.phase == "select" and index<arena.tactical.enemy_preview.size():
			return {"state":"masked","slot":index+1}
		return {"state":"empty","slot":index+1}
	var card: Dictionary = TDefs.card(String(id))
	var stat := "%d伤 · %s" % [card.damage,card.speed_label] if card.attack else "%s · %d帧" % [_kind_label(String(card.kind)),card.windup]
	return {"state":"visible","slot":index+1,"name":String(card.name),"rank":int(card.rank),"stat":stat,"kind":String(card.kind),"mark":_action_mark(String(card.kind))}

func card_detail(id: String) -> Dictionary:
	var card: Dictionary = TDefs.card(id)
	if card.is_empty():
		return {}
	return {"name":String(card.name),"body":String(card.text),"meta":"%s · 点数 %d · 起手 %d帧" % [card.speed_label,card.rank,card.windup]+(" · 伤害 %d" % card.damage if card.attack else "")}

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
	return Rect2(1384,668,168,34)

func undo_rect() -> Rect2:
	return Rect2(1252,668,120,34)

func pause_rect() -> Rect2:
	return Rect2(660,94,128,32)

func restart_rect() -> Rect2:
	return Rect2(812,94,128,32)

func _joker_rect(role: String,index: int) -> Rect2:
	return Rect2((48.0 if role == "player" else 940.0)+float(index)*208.0,122.0,196.0,36.0)

func focus_card(index: int) -> void:
	keyboard_focus_index = index

func _changed() -> void:
	arena._mirror_tactical()
	arena.force_redraw()

func handle_click(at: Vector2) -> bool:
	var m = arena.tactical
	if restart_rect().has_point(at) or (m.phase == "match_over" and confirm_rect().has_point(at)):
		arena._start_tactical_match()
		return true
	if pause_rect().has_point(at):
		arena.paused = not arena.paused
		m.paused = arena.paused
		_changed()
		return true
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
	var mouse := get_global_mouse_position()
	if mouse.distance_to(_last_mouse)>1.0 or m.phase != _last_phase:
		keyboard_focus_index = -1
	_last_mouse = mouse
	_last_phase = m.phase
	hover_kind = ""
	hover_index = -1
	hover_role = "player"
	if m.phase != "loadout":
		for i in range(m.hand.size()):
			if m.hand[i] != null and hand_rect(i).has_point(mouse):
				hover_kind = "card"
				hover_index = i
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
	return super._visual_key()+str([hover_kind,hover_index,hover_role,keyboard_focus_index])+(arena.tactical.signature() if arena != null and arena.tactical != null else "")

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
	draw_rect(rect,GOLD if enabled and primary else Color(0.10,0.12,0.17,0.98))
	draw_rect(rect,GOLD if enabled else Color(0.30,0.35,0.43),false,1.0)
	_center(label,rect,17,Color(0.09,0.08,0.06) if enabled and primary else (INK if enabled else SECONDARY))

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
		draw_rect(Rect2(0,174,1600,726),Color(0.01,0.02,0.04,0.66))
		_center("已暂停 · P 或上方按钮继续",Rect2(480,400,640,74),30,GOLD)
	draw_set_transform(Vector2.ZERO,0.0,Vector2(1.25,1.25))
	_draw_profile()
	draw_set_transform(Vector2.ZERO)
	arena.redraw_stats.hud_draw_us += Time.get_ticks_usec()-started

func _draw_header() -> void:
	var m = arena.tactical
	draw_rect(Rect2(0,0,1600,168),Color(0.035,0.045,0.075,0.92))
	_draw_bar_v2(Vector2(112,44),arena.player.hp_ratio(),float(_hp_shown.p),false,"你",true)
	_draw_bar_v2(Vector2(1036,44),arena.enemy.hp_ratio(),float(_hp_shown.e),true,"青岚",false)
	_draw_rage_bar(Vector2(112,78),float(m.state.player.rage)/100.0,false)
	_draw_rage_bar(Vector2(1036,78),float(m.state.foe.rage)/100.0,true)
	_text("怒火 %d%%" % int(m.state.player.rage)+(" · EX准备" if float(m.state.player.rage)>=100.0 else ""),Vector2(112,110),15,SECONDARY)
	var rage_label := "怒火 %d%%" % int(m.state.foe.rage)+(" · EX准备" if float(m.state.foe.rage)>=100.0 else "")
	_text(rage_label,Vector2(1488-font.get_string_size(rage_label,HORIZONTAL_ALIGNMENT_LEFT,-1,15).x,110),15,SECONDARY)
	_center("第 %d 局" % m.round_index,Rect2(704,8,192,26),18,SECONDARY)
	_center("%d : %d" % [m.wins[0],m.wins[1]],Rect2(704,38,192,42),34,INK)
	_button(pause_rect(),"继续 P" if arena.paused else "暂停 P",true,false)
	_button(restart_rect(),"重开 R",true,false)
	_center("第 %d 轮 / %d" % [m.turn_index,TDefs.TURNS],Rect2(704,136,192,24),16,SECONDARY)
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
				draw_rect(rect,GOLD if triggered != "" else joker.color,false,2.0 if triggered != "" else 1.0)
				_text(str(index+1),rect.position+Vector2(12,25),15,joker.color)
				_text(String(joker.name),rect.position+Vector2(34,25),18,INK)
				if triggered != "":
					_text(triggered,Vector2(rect.end.x-12-font.get_string_size(triggered,HORIZONTAL_ALIGNMENT_LEFT,-1,14).x,rect.position.y+25),14,GOLD)
			else:
				draw_rect(rect,Color(0.28,0.33,0.41),false,1.0)
				_center("待装备小丑",rect,16,SECONDARY)

func _draw_loadout() -> void:
	var m = arena.tactical
	draw_rect(Rect2(100,174,1400,700),SURFACE)
	draw_rect(Rect2(100,174,1400,700),Color(0.49,0.43,0.31),false,1.0)
	_text("选择战术小丑",Vector2(136,224),32,GOLD)
	_text("六选三 · 左到右触发 · 再次点击取消，退格撤销",Vector2(136,253),18,SECONDARY)
	for index in range(m.offers.size()):
		var rect := offer_rect(index)
		var joker: Dictionary = TDefs.joker(m.offers[index])
		var picked: bool = m.selected.has(index)
		draw_rect(rect,Color(0.13,0.12,0.10) if picked else Color(0.08,0.095,0.14))
		draw_rect(rect,GOLD if picked else joker.color,false,2.0 if picked else 1.0)
		_text(String(joker.name),rect.position+Vector2(22,42),28,INK)
		_text("按键 %d" % (index+1),rect.position+Vector2(rect.size.x-88,38),16,joker.color)
		var lines: Array = _wrap_pixels(String(joker.text),rect.size.x-44,18)
		for line in range(mini(3,lines.size())):
			_text(lines[line],rect.position+Vector2(22,78+float(line)*25),18,SECONDARY)
		if picked:
			_text("第 %d 位" % (m.selected.find(index)+1),rect.position+Vector2(rect.size.x-96,138),16,GOLD)
	for index in range(TDefs.JOKER_SLOTS):
		var rect := Rect2(136+float(index)*448,656,432,58)
		draw_rect(rect,Color(0.08,0.085,0.12))
		draw_rect(rect,Color(0.46,0.40,0.28),false,1.0)
		var label := "%d · " % (index+1)+(String(TDefs.joker(m.offers[m.selected[index]]).name) if index<m.selected.size() else "选择小丑")
		_center(label,rect,22,GOLD if index<m.selected.size() else SECONDARY)
	_text("同一套小丑贯穿三局；加伤与倍率按摆放顺序连锁。",Vector2(136,753),18,SECONDARY)
	_text("装备后直接读牌：从八张手牌编排五招，敌方明三张、暗两张。",Vector2(136,783),17,SECONDARY)
	_button(confirm_rect(),"装备小丑 · 空格" if m.selected.size()==TDefs.JOKER_SLOTS else "还需选 %d 张" % (TDefs.JOKER_SLOTS-m.selected.size()),m.selected.size()==TDefs.JOKER_SLOTS)

func _draw_plans() -> void:
	_draw_plan_row("player")
	_draw_plan_row("foe")

func _draw_plan_row(role: String) -> void:
	var m = arena.tactical
	var player_side: bool = role == "player"
	var header_y := 199.0 if player_side else 293.0
	var label := "你 · %s" % TDefs.distance_label(int(m.state.distance)) if player_side else "青岚 · %d明 %d隐" % [TDefs.PLAY-TDefs.ENEMY_HIDDEN,TDefs.ENEMY_HIDDEN] if m.phase == "select" else "青岚"
	_text(label,Vector2(PLAN_LEFT,header_y),17,INK)
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
		draw_rect(rect,SURFACE)
		if face.state == "visible":
			draw_rect(Rect2(rect.position,Vector2(3.0,rect.size.y)),outline)
		elif face.state == "masked":
			draw_texture_rect(HIDDEN_MARK,rect,false,Color(0.72,0.73,0.82,0.25))
		draw_rect(rect,outline,false,2.0 if active else 1.0)
		var badge := Rect2(rect.position+Vector2(8,9),Vector2(28,22))
		draw_rect(badge,Color(card_color.r,card_color.g,card_color.b,0.20))
		_center("%02d" % slot,badge,12,GOLD if active else card_color)
		if face.state == "visible":
			_text(String(face.mark),rect.position+Vector2(rect.size.x-22,19),12,card_color)
			_text(str(face.rank),rect.position+Vector2(rect.size.x-43,19),13,SECONDARY)
			_center(String(face.name),Rect2(rect.position+Vector2(38,9),Vector2(rect.size.x-48,25)),18,INK)
			_center(String(face.stat),Rect2(rect.position+Vector2(44,33),Vector2(rect.size.x-52,17)),12,SECONDARY)
		elif face.state == "masked":
			_center("?",Rect2(rect.position+Vector2(rect.size.x*0.5-18,5),Vector2(36,54)),42,INK)
		else:
			_center("＋",Rect2(rect.position+Vector2(rect.size.x*0.5-15,8),Vector2(30,40)),26,Color(0.56,0.61,0.71))
	if hidden_count == 0 and plan.size() == TDefs.PLAY:
		var complete := true
		for id in plan:
			complete = complete and id != null
		if complete:
			var pattern: Dictionary = m.patterns.get(role,TDefs.evaluate(plan)) if m.phase != "select" else TDefs.evaluate(plan)
			var label_pattern := "%s  +%d  ×%.2f" % [pattern.name,pattern.flat,pattern.mult]
			var x := 1552.0-_regular_font.get_string_size(label_pattern,HORIZONTAL_ALIGNMENT_LEFT,-1,15).x
			_text(label_pattern,Vector2(x,header_y),15,GOLD)


func _draw_tactical_hand() -> void:
	var m = arena.tactical
	draw_rect(Rect2(0,656,1600,244),Color(0.035,0.045,0.07,0.94))
	draw_line(Vector2(48,657),Vector2(1552,657),Color(0.36,0.39,0.48,0.70),1.0)
	var hand_title := "手牌  %d" % m.hand.filter(func(id): return id != null).size()
	_text(hand_title,Vector2(48,690),18,INK)
	var selected_label := "%d / %d" % [m.selected.size(),TDefs.PLAY] if m.phase == "select" else ""
	_text(selected_label,Vector2(178,689),15,GOLD)
	if m.phase == "select":
		var change_label := "换牌 %d / %d" % [m.swaps_used,TDefs.DISCARD_MAX]
		_text(change_label,Vector2(1058,689),14,SECONDARY)
		_button(undo_rect(),"撤回",not m.selected.is_empty(),false)
		var enabled: bool = m.selected.size()==TDefs.PLAY
		_button(confirm_rect(),"开打" if enabled else "选牌 %d/%d" % [m.selected.size(),TDefs.PLAY],enabled)
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
		draw_rect(Rect2(rect.position,Vector2(2.0,rect.size.y)),accent)
		if picked:
			var number: String = "%02d" % int(face.step)
			var badge := Rect2(rect.position+Vector2(10,10),Vector2(31,25))
			draw_rect(badge,Color(GOLD.r,GOLD.g,GOLD.b,0.18))
			_center(number,badge,14,GOLD)
		else:
			var mark_box := Rect2(rect.position+Vector2(10,10),Vector2(26,24))
			draw_rect(mark_box,Color(accent.r,accent.g,accent.b,0.15))
			_center(String(face.mark),mark_box,14,accent)
		_text(str(face.rank),rect.position+Vector2(rect.size.x-29,30),23,SECONDARY)
		_text(String(face.name),rect.position+Vector2(11,69),21 if rect.size.x>=160.0 else 19,INK)
		var stat_rect := Rect2(rect.position+Vector2(11,88),Vector2(rect.size.x-22,25))
		_text(String(face.stat),stat_rect.position+Vector2(0,17),14,accent)
		draw_line(rect.position+Vector2(11,123),rect.end+Vector2(-11,-49),Color(accent.r,accent.g,accent.b,0.32),1.0)
		if m.phase == "select":
			var enabled: bool = m.swaps_used<TDefs.DISCARD_MAX
			var button := swap_card_rect(index)
			draw_rect(button,Color(0.07,0.08,0.11,0.96))
			draw_rect(button,GOLD if enabled else Color(0.28,0.33,0.41),false,1.0)
			_center("↻",button,16,GOLD if enabled else SECONDARY)

func _draw_actor_status() -> void:
	var m = arena.tactical
	for role in ["player","foe"]:
		var fighter = arena.player if role == "player" else arena.enemy
		var labels: Array = []
		if m.state[role].exposed:
			labels.append("破绽 · 可确反")
		if m.state[role].focus:
			labels.append("蓄势 +3")
		if not labels.is_empty():
			var rect := Rect2(fighter.global_position.x-116,474,232,28)
			draw_rect(rect,SURFACE)
			_center(" / ".join(PackedStringArray(labels)),rect,16,GOLD)

func _draw_sources() -> void:
	var m = arena.tactical
	if m.phase != "resolve" or hover_kind != "":
		return
	for role in ["player","foe"]:
		for hit in m.latest_hits:
			if hit.source != role or int(hit.damage)<=0:
				continue
			var left := 48.0 if role == "player" else 1216.0
			draw_rect(Rect2(left,478,336,122),SURFACE)
			_text(TDefs.outcome_label(String(hit.kind))+" · %d伤害" % int(hit.damage),Vector2(left+16,508),22,GOLD)
			var pieces: Array = []
			for part in hit.parts:
				pieces.append(String(part.name)+(str(int(part.value)) if part.op=="base" else String(part.op)+("%.2f" % float(part.value) if part.op=="×" else str(int(part.value)))))
			var lines: Array = _wrap_pixels(" → ".join(PackedStringArray(pieces)),304,15)
			for i in range(mini(3,lines.size())):
				_text(lines[i],Vector2(left+16,539+float(i)*21),15,SECONDARY)

func _draw_tooltip() -> void:
	var m = arena.tactical
	var title := ""
	var body := ""
	var metadata := ""
	var id = null
	if hover_kind == "card" and hover_index>=0 and hover_index<m.hand.size():
		id = m.hand[hover_index]
	elif hover_kind == "plan":
		id = plan_card(hover_role,hover_index)
		if id == null and hover_role == "foe" and m.phase == "select":
			title = "暗牌 · 第%d拍" % (hover_index+1)
			body = "对手已锁定，开打时揭晓。"
			metadata = "随机隐藏"
	if id != null:
		var detail: Dictionary = card_detail(String(id))
		title = String(detail.name)
		body = String(detail.body)
		metadata = String(detail.meta)
	elif hover_kind == "joker" and hover_index>=0 and hover_index<m.state[hover_role].jokers.size():
		var joker: Dictionary = TDefs.joker(m.state[hover_role].jokers[hover_index])
		title = joker.name
		body = joker.text
		metadata = "按槽位顺序触发"
	if title == "":
		return
	var rect := Rect2(48.0 if hover_role == "player" else 1216.0,446,336,188)
	draw_rect(rect,SURFACE)
	draw_rect(rect,Color(0.49,0.52,0.62),false,1.0)
	_text(title,rect.position+Vector2(16,34),24,INK)
	_text(metadata,rect.position+Vector2(16,61),14,GOLD)
	var lines: Array = _wrap_pixels(body,304,16)
	for i in range(mini(4,lines.size())):
		_text(lines[i],rect.position+Vector2(16,91+float(i)*21),16,SECONDARY)

func _draw_match_end() -> void:
	var m = arena.tactical
	draw_rect(Rect2(550,384,500,238),SURFACE)
	draw_rect(Rect2(550,384,500,238),GOLD,false,1.0)
	_center(String(m.notice),Rect2(570,408,460,58),34,GOLD)
	_center("战绩 %d : %d" % [m.wins[0],m.wins[1]],Rect2(570,485,460,32),22,SECONDARY)
	_button(confirm_rect(),"重新构筑 · R")

func _draw_footer() -> void:
	var m = arena.tactical
	var left := "1–0 编排   Shift + 数字 换牌   Backspace 撤回"
	if m.phase == "loadout":
		left = "1–6 选择小丑   Backspace 撤回"
	_text(left,Vector2(48,896),13,SECONDARY)
	var counts: Dictionary = m.deck_counts("player")
	var right := "牌堆 %d · 弃牌 %d" % [counts.draw,counts.discard]
	_text(right,Vector2(1552-font.get_string_size(right,HORIZONTAL_ALIGNMENT_LEFT,-1,13).x,896),13,SECONDARY)
