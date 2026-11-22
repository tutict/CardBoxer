extends SceneTree
const Motion = preload("res://scripts/native_motion.gd")
const Flow = preload("res://scripts/battle_presentation.gd")
const Defs = preload("res://scripts/card_data.gd")
func _initialize():
 call_deferred("run")
func run():
 var lib=Motion.new()
 if not lib.load_data():
  push_error(lib.last_error)
  quit(1)
  return
 lib.prepare_support()
 var largest=0.0
 var smallest=0.0
 var worst={}
 var samples=0
 for role in ["player","foe"]:
  for walk_step in range(8):
   for cid in Defs.CARDS:
    var flow=Flow.new()
    flow.setup(lib)
    flow.reset(1)
    var context={"mode":"realtime"}
    var phase=float(walk_step)/8.0
    flow.sample(role,{"state":0,"walk_blend":1.0,"walk_phase":phase,"action_seq":0},context)
    flow.sample(role,{"state":1,"card_id":cid,"phase":"windup","phase_progress":0.0,"action_seq":1},context)
    for step in range(1,7):
     var dt=.01
     flow.advance(dt,context)
     var time=step*.01
     var visual=flow.sample(role,{"state":1,"card_id":cid,"phase":"windup","phase_progress":clampf(time/(float(Defs.card(cid).windup)*Defs.FRAME),0.0,1.0),"action_seq":1},context)
     var sole=lib.support_height(role,visual.pose)
     samples+=1
     smallest=minf(smallest,sole)
     if absf(sole)>largest:
      largest=absf(sole)
      worst={"role":role,"walk_phase":phase,"card":cid,"time":time,"height_m":sole}
 print("NATURAL REVIEW TRANSITION SUPPORT ",JSON.stringify({"samples":samples,"max_abs_m":largest,"min_m":smallest,"worst":worst}))
 quit(0)
