"""A real geometry test: equal authored hands must be mirrored in every state."""
import bpy,json,os
from mathutils import Vector
O=os.path.dirname(os.path.abspath(__file__));bpy.ops.wm.open_mainfile(filepath=O+'/player-retopology.blend');ob=bpy.data.objects['PLAYER_Retopo_Game_Quads'];meta=json.load(open(O+'/hand-authoring.json'));bc=meta['body_vertex_count'];f=meta['hand_models']['f'];b=meta['hand_models']['b'];out={}
for g in [0,.25,.5,.75,1]:
 h=2*g if g<=.5 else 2*(1-g);c=0 if g<=.5 else 2*g-1;errors=[]
 for a in range(f['end']-f['start']):
  points=[]
  for role,m in [('f',f),('b',b)]:
   i=bc+m['start']+a;p=ob.data.vertices[i].co.copy();p+=h*(ob.data.shape_keys.key_blocks['grip_half_'+role].data[i].co-p)+c*(ob.data.shape_keys.key_blocks['grip_'+role].data[i].co-ob.data.vertices[i].co);points.append(p)
  points[1].x*=-1;errors.append((points[0]-points[1]).length)
 out[str(g)]=max(errors)
json.dump(out,open(O+'/hand-symmetry-acceptance.json','w'),indent=2);print(out)
assert max(out.values())<1e-6,'FAIL: rear-hand normal frame is not a reflection of front hand'
