import bpy,bmesh,json,os,math,numpy as np,hashlib
from mathutils import Vector
from mathutils.bvhtree import BVHTree
O=os.path.dirname(os.path.abspath(__file__));bpy.ops.wm.open_mainfile(filepath=O+'/player-retopology.blend')
low=bpy.data.objects['PLAYER_Retopo_Game_Quads'];src=bpy.data.objects['SOURCE_player_immutable'];arm=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE' and len(o.data.bones)==14)
meta=json.load(open(O+'/hand-authoring.json'));bc=meta['body_vertex_count'];bvh=BVHTree.FromPolygons([v.co for v in src.data.vertices],[tuple(p.vertices) for p in src.data.polygons],all_triangles=True)
checks={};checks['mesh_triangles']=sum(len(p.vertices)-2 for p in low.data.polygons);checks['triangle_cap_pass']=checks['mesh_triangles']<=80000
errs=[];influences=[];neutral=0
for v in low.data.vertices:
 w=[g.weight for g in v.groups if low.vertex_groups[g.group].name in arm.data.bones and low.vertex_groups[g.group].name!='neutral_bone'];errs.append(abs(sum(w)-1));influences.append(len(w));neutral+=sum(g.weight for g in v.groups if low.vertex_groups[g.group].name=='neutral_bone')
checks['max_normalization_error']=max(errs);checks['max_influences']=max(influences);checks['neutral_weight_sum']=neutral;checks['weights_pass']=max(errs)<1e-5 and max(influences)<=4 and neutral==0
handsets={r:set(range(bc+m['start'],bc+m['end'])) for r,m in meta['hand_models'].items()};checks['morphs']={}
for k in low.data.shape_keys.key_blocks:
 if k.name=='Basis':continue
 role=k.name[-1];nz=[i for i,d in enumerate(k.data) if (d.co-low.data.vertices[i].co).length>1e-9];outside=[i for i in nz if i not in handsets[role]]
 checks['morphs'][k.name]={'moved_vertices':len(nz),'nonhand_deltas':len(outside),'default':k.value,'pass':bool(nz) and not outside and k.value==0}
checks['grip_states']=[]
for g in [0,.25,.5,.75,1]:
 coords=[v.co.copy() for v in low.data.vertices]
 for role,ids in handsets.items():
  half=low.data.shape_keys.key_blocks['grip_half_'+role];full=low.data.shape_keys.key_blocks['grip_'+role];h=2*g if g<=.5 else 2*(1-g);f=0 if g<=.5 else 2*g-1
  for i in ids:coords[i]+=h*(half.data[i].co-low.data.vertices[i].co)+f*(full.data[i].co-low.data.vertices[i].co)
 finite=all(math.isfinite(c) for v in coords for c in v);lengths=[(coords[e.vertices[0]]-coords[e.vertices[1]]).length for e in low.data.edges if all(i in handsets['f'] or i in handsets['b'] for i in e.vertices)]
 checks['grip_states'].append({'grip':g,'finite':finite,'max_hand_edge_m':max(lengths),'pass':finite and max(lengths)<.07})
bm=bmesh.new();bm.from_mesh(low.data);checks['boundary_edges']=sum(e.is_boundary for e in bm.edges);checks['nonmanifold_edges']=sum(not e.is_manifold for e in bm.edges);bm.free()
sole=[bvh.find_nearest(v.co)[3] for v in low.data.vertices if v.co.z<.05];checks['max_sole_deviation_m']=max(sole);checks['sole_pass']=max(sole)<=.02
checks['textures']={}
for name in ['player-basecolor-4k','player-normal-4k','player-orm-4k']:
 im=bpy.data.images[name];checks['textures'][name]={'size':list(im.size),'pass':list(im.size)==[4096,4096]}
checks['bone_names']=[b.name for b in arm.data.bones];checks['pass']=checks['triangle_cap_pass'] and checks['weights_pass'] and all(c['pass'] for c in checks['morphs'].values()) and all(c['pass'] for c in checks['grip_states']) and checks['sole_pass'] and all(c['pass'] for c in checks['textures'].values()) and checks['boundary_edges']==0
json.dump(checks,open(O+'/authoring-validation.json','w'),indent=2);print(json.dumps(checks,indent=2))
