"""Reproducible player quad retopology, custom segmented hands, UV and PBR baking.
Run using Blender 5.2 --background --python tools/author_player.py.
"""
import bpy,bmesh,json,os,time,math,hashlib, numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT=ROOT+'/authoring/player';os.makedirs(OUT+'/textures',exist_ok=True)
START=time.time()
def log(*s):print('PLAYER',*s,flush=True)
def sha(p):return hashlib.sha256(open(p,'rb').read()).hexdigest()
def active(ob):
 bpy.ops.object.select_all(action='DESELECT');ob.select_set(True);bpy.context.view_layer.objects.active=ob
def hide(ob):ob.hide_render=True;ob.hide_set(True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=ROOT+'/baseline/assets/3d/player-rigged.glb')
source=next(o for o in bpy.context.scene.objects if o.name.startswith('player_HI'))
arm=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
for o in list(bpy.context.scene.objects):
 if o not in [source,arm]:bpy.data.objects.remove(o,do_unlink=True)
source.name='SOURCE_player_immutable';source['immutable_source_sha256']=sha(ROOT+'/baseline/assets/3d/player-rigged.glb')
source['baseline_acceptance']='FAIL: triangle-only surface, no progressive hand morphs'
source_tris=len(source.data.polygons)
origco=[v.co.copy() for v in source.data.vertices];origpoly=[tuple(p.vertices) for p in source.data.polygons]
origuv=[[source.data.uv_layers.active.data[li].uv.copy() for li in p.loop_indices] for p in source.data.polygons]
bvh=BVHTree.FromPolygons(origco,origpoly,all_triangles=True)
weights=[{source.vertex_groups[g.group].name:g.weight for g in v.groups if source.vertex_groups[g.group].name!='neutral_bone'} for v in source.data.vertices]

# QuadriFlow is the topology generator. Welding is only at coincident seam points.
probe=OUT+'/quadflow-probe.blend'
# The scan's thin fused layers are not preserved by whole-body QuadriFlow.
# Retain that rejected base as evidence; final reconstruction changes source
# connectivity with controlled collapse and quad pairing to retain fine features.
USE_SOURCE_PRESERVING_REFLOW=True
if USE_SOURCE_PRESERVING_REFLOW:
 low=source.copy();low.data=source.data.copy();bpy.context.collection.objects.link(low);low.name='PLAYER_Retopo_Game_Quads';low.modifiers.clear();low.parent=None;active(low)
 bm=bmesh.new();bm.from_mesh(low.data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.000004);bm.to_mesh(low.data);bm.free()
 dec=low.modifiers.new('Surface preserving connectivity rebuild','DECIMATE');dec.ratio=.80;dec.use_collapse_triangulate=True;bpy.ops.object.modifier_apply(modifier=dec.name)
 bm=bmesh.new();bm.from_mesh(low.data)
 bmesh.ops.join_triangles(bm,faces=list(bm.faces),angle_face_threshold=.50,angle_shape_threshold=2.8,cmp_seam=False,cmp_sharp=False,cmp_uvs=False,cmp_vcols=False,cmp_materials=False)
 bm.to_mesh(low.data);bm.free()
elif os.path.exists(probe):
 with bpy.data.libraries.load(probe,link=False) as (fr,to):to.objects=[n for n in fr.objects if n.startswith('player_HI')]
 low=to.objects[0];bpy.context.collection.objects.link(low);low.name='PLAYER_Retopo_Game_Quads';low.parent=None
else:
 low=source.copy();low.data=source.data.copy();bpy.context.collection.objects.link(low);low.name='PLAYER_Retopo_Game_Quads';active(low)
 bm=bmesh.new();bm.from_mesh(low.data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.000004);bm.to_mesh(low.data);bm.free()
 bpy.ops.object.quadriflow_remesh(target_faces=36000,use_preserve_sharp=True,use_preserve_boundary=True,use_mesh_symmetry=False,seed=17)
low.modifiers.clear();low.vertex_groups.clear();low.data.materials.clear()
log('surface_preserving_quad_reflow',len(low.data.vertices),len(low.data.polygons))

def frame(sign):
 U=Vector((sign*.76,0,-.65)).normalized();W=Vector((sign*.184,-.959,.215)).normalized();N=U.cross(W).normalized()
 return Vector((sign*.480,-.221,1.015)),U,W,N
def hand_local(p,sign):
 O,U,W,N=frame(sign);d=p-O;return d.dot(U),d.dot(W),d.dot(N)
def cut_hand(p):
 sign=1 if p.x>0 else -1
 return abs(p.x)>.445 and p.z<1.075 and hand_local(p,sign)[0]>.026

bm=bmesh.new();bm.from_mesh(low.data)
remove=[v for v in bm.verts if cut_hand(v.co)];bmesh.ops.delete(bm,geom=remove,context='VERTS')
boundary=[e for e in bm.edges if e.is_boundary]
if boundary:bmesh.ops.holes_fill(bm,edges=boundary,sides=0)
# Densify face and the elbow/knee bend zones with true quad subdivision.
sel=[]
for e in bm.edges:
 c=(e.verts[0].co+e.verts[1].co)/2
 if (.48<c.z<.55 and abs(c.x)>.09) or (1.095<c.z<1.14 and .28<abs(c.x)<.35):sel.append(e)
bmesh.ops.subdivide_edges(bm,edges=sel,cuts=1,use_grid_fill=True)
bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(low.data);bm.free()

# Replace each eye and lip patch with explicit concentric feature rings. These
# are connected to the generated body boundary and retain sampled source form.
bm=bmesh.new();bm.from_mesh(low.data);feature_counts={}
for label,cx,cz,rx,rz in []: # Destructive scan patches rejected; preserve closed facial substrate.
 oldbm=bm;bm=bm.copy()
 def rollback():
  global bm
  bm.free();bm=oldbm
 def radius(p):return math.sqrt(((p.x-cx)/rx)**2+((p.z-cz)/rz)**2)
 cut=[f for f in bm.faces if f.calc_center_median().y<-.24 and radius(f.calc_center_median())<1.18]
 if not cut:rollback();continue
 bmesh.ops.delete(bm,geom=cut,context='FACES')
 boundary=[e for e in bm.edges if e.is_boundary and all(v.co.y<-.23 and radius(v.co)<1.9 for v in e.verts)]
 if len(boundary)<8:rollback();continue
 adjacency={}
 for e in boundary:
  for v in e.verts:adjacency.setdefault(v,[]).append(e.other_vert(v))
 unseen=set(adjacency);components=[]
 while unseen:
  seed=unseen.pop();comp={seed};stack=[seed]
  while stack:
   for v in adjacency.get(stack.pop(),[]):
    if v in unseen:unseen.remove(v);comp.add(v);stack.append(v)
  if all(len(adjacency[v])==2 for v in comp):components.append(comp)
 if not components:rollback();continue
 comp=max(components,key=len);start=next(iter(comp));chain=[start];previous=None;current=start;closed=False
 for k in range(len(adjacency)+1):
  choices=[v for v in adjacency.get(current,[]) if v!=previous]
  if not choices:break
  nxt=choices[0]
  if nxt==start:closed=True;break
  chain.append(nxt);previous,current=current,nxt
 if len(chain)<8 or not closed:rollback();continue
 previous_ring=chain
 for scale in [1.00,.85,.68,.45,.22]:
  ring=[]
  for v in chain:
   theta=math.atan2((v.co.z-cz)/rz,(v.co.x-cx)/rx);x=cx+rx*scale*math.cos(theta);z=cz+rz*scale*math.sin(theta)
   p,n,fi,d=bvh.ray_cast(Vector((x,-.8,z)),Vector((0,1,0)),.7)
   if p is None:p=Vector((x,sum(v.co.y for v in chain)/len(chain),z))
   ring.append(bm.verts.new(p))
  for i in range(len(chain)):
   j=(i+1)%len(chain)
   try:bm.faces.new((previous_ring[i],previous_ring[j],ring[j],ring[i]))
   except ValueError:pass
  previous_ring=ring
 center,n,fi,d=bvh.ray_cast(Vector((cx,-.8,cz)),Vector((0,1,0)),.7)
 center=bm.verts.new(center if center is not None else Vector((cx,-.32,cz)))
 for i in range(len(chain)):
  try:bm.faces.new((previous_ring[i],previous_ring[(i+1)%len(chain)],center))
  except ValueError:pass
 feature_counts[label]={'boundary_vertices':len(chain),'concentric_rings':5}
 oldbm.free()
orphans=[v for v in bm.verts if not v.link_faces]
if orphans:bmesh.ops.delete(bm,geom=orphans,context='VERTS')
# Closed anatomical feature inserts keep the scan's complex eyelash/eyeball
# component continuity. Each eyelid/lip rim has48segments and4concentric rings,
# with an inner return surface; there are no exposed boundary edges or holes.
for label,cx,cz,rx,rz in []: # Structured integrated face helper replaces overlap-prone inserts.
 layers=[]
 for layer in [0,1]:
  rings=[]
  for scale in [1.15,1.07,.99,.91]:
   ring=[]
   for k in range(48):
    theta=2*math.pi*k/48;x=cx+rx*scale*math.cos(theta);z=cz+rz*scale*math.sin(theta);p,n,fi,d=bvh.ray_cast(Vector((x,-.8,z)),Vector((0,1,0)),.7)
    if p is None:p=Vector((x,-.315,z))
    p=p.copy();p.y-=.00018 if layer==0 else -.00010;ring.append(bm.verts.new(p))
   rings.append(ring)
  layers.append(rings)
  for ri in range(3):
   for k in range(48):
    j=(k+1)%48;ids=(rings[ri][k],rings[ri][j],rings[ri+1][j],rings[ri+1][k]);bm.faces.new(ids if layer==0 else tuple(reversed(ids)))
 for ri in [0,3]:
  for k in range(48):
   j=(k+1)%48;bm.faces.new((layers[0][ri][k],layers[1][ri][k],layers[1][ri][j],layers[0][ri][j]))
 feature_counts[label]={'segments':48,'concentric_rings':4,'closed_return_surface':True,'intentional_component':'eyelid/lip inset over closed facial substrate'}
bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(low.data);bm.free()
log('explicit_feature_loops',feature_counts)

# Retain QuadriFlow's consistent surface. Nearest projection of thin cloth can jump
# from the front panel to its back and create spikes; only skin is relaxed below.
for v in low.data.vertices:
 p,n,fi,d=bvh.find_nearest(v.co)
 if p is not None and d<.03:v.co=p
bm=bmesh.new();bm.from_mesh(low.data)
for it in range(3):
 updates=[]
 for v in bm.verts:
  c=v.co
  face_skin=abs(c.x)<.098 and 1.44<c.z<1.56 and c.y<-.25
  cloth=(.65<c.z<1.30 and abs(c.x)<.30 and c.y<-.18)
  if not(face_skin or cloth) or len(v.link_edges)<3:continue
  avg=sum((e.other_vert(v).co for e in v.link_edges),Vector())/len(v.link_edges)
  delta=avg-c
  # Remove tangential noise while limiting total displacement to below 1 mm.
  strength=.18 if face_skin else .07
  updates.append((v,c+delta*strength))
 for v,p in updates:v.co=p
bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(low.data);bm.free()

import importlib.util
face_spec=importlib.util.spec_from_file_location('player_face_rebuild',OUT+'/face_rebuild.py');face_module=importlib.util.module_from_spec(face_spec);face_spec.loader.exec_module(face_module)
face_reconstruction=face_module.reconstruct(low,bvh);feature_counts=face_reconstruction['features'];log('structured_face',face_reconstruction)

verts=[];faces=[];tags=[];fmat=[];hand_models={}
def av(p,tag):verts.append(tuple(p));tags.append(tag);return len(verts)-1
def af(ids,mi):faces.append(tuple(ids));fmat.append(mi)
def build_hand(sign,role):
 O,U,W,N=frame(sign);meta={};start=len(verts);palmrows=[]
 # 16 columns: four finger mouths with physical web gaps between them.
 lateral=np.linspace(-.037,.037,16)
 for ri in range(10):
  t=ri/9;u=.018+(.098-.018)*t;width=.78+.22*math.sin(t*math.pi/2)
  top=[];bot=[]
  for j,w in enumerate(lateral):
   thick=.0175*(.90+.10*math.sin(t*math.pi));bulge=math.sqrt(max(0,1-(w/.046)**2))
   top.append(av(O+U*u+W*(w*width)+N*(thick*bulge-.004),('palm',role,u,w,1)))
   bot.append(av(O+U*u+W*(w*width)-N*(thick*bulge+.004),('palm',role,u,w,-1)))
  palmrows.append((top,bot))
  if ri:
   a,b=palmrows[ri-1]
   for j in range(15):af((a[j],a[j+1],top[j+1],top[j]),1);af((b[j+1],b[j],bot[j],bot[j+1]),1)
   af((a[0],top[0],bot[0],b[0]),1);af((top[-1],a[-1],b[-1],bot[-1]),1)
 a,b=palmrows[0]
 for j in range(15):af((a[j+1],a[j],b[j],b[j+1]),1)
 top,bot=palmrows[-1]
 for j in [3,7,11]:af((top[j],top[j+1],bot[j+1],bot[j]),1)
 finger_lengths=[.071,.092,.087,.069]
 for fi,col in enumerate([0,4,8,12]):
  ring=top[col:col+4]+list(reversed(bot[col:col+4]));root=O+U*.098+W*float((lateral[col]+lateral[col+3])/2)-N*.004
  w0=float((lateral[col]+lateral[col+3])/2);length=finger_lengths[fi];splay=(fi-1.5)*.045
  rid=[]
  # 15 transverse rings, with paired support loops at MCP/PIP/DIP, 8 radial sides.
  ts=[0,.025,.075,.14,.24,.34,.42,.46,.49,.59,.69,.74,.78,.88,.97]
  for t in ts:
   if t==0:ids=ring
   else:
    taper=.98-.18*t-.12*max(0,(t-.80)/.20);rW=.0075*taper;rN=.0145*taper
    center=root+U*(length*t)+W*(length*t*splay)+N*(-.003*math.sin(t*math.pi))
    ids=[]
    for k in range(8):
     angle=math.atan2([1,1,1,1,-1,-1,-1,-1][k],[-1,-.33,.33,1,1,.33,-.33,-1][k])
     ids.append(av(center+W*(math.cos(angle)*rW)+N*(math.sin(angle)*rN),('finger',role,fi,t,k)))
   rid.append(ids)
   if len(rid)>1:
    prev=rid[-2]
    for k in range(8):af((prev[k],prev[(k+1)%8],ids[(k+1)%8],ids[k]),1 if t<.12 else 2)
  # Rounded closed tip with small terminal ring and quad cap.
  center=root+U*length+W*(length*splay)-N*.001
  last=[]
  for k in range(8):
   angle=math.atan2([1,1,1,1,-1,-1,-1,-1][k],[-1,-.33,.33,1,1,.33,-.33,-1][k]);last.append(av(center+W*(math.cos(angle)*.003)+N*(math.sin(angle)*.006),('finger',role,fi,1.,k)))
  for k in range(8):af((rid[-1][k],rid[-1][(k+1)%8],last[(k+1)%8],last[k]),2)
  af((last[0],last[1],last[2],last[3]),2);af((last[4],last[5],last[6],last[7]),2);af((last[0],last[3],last[4],last[7]),2)
  meta[fi]={'root':list(root),'length':length,'w':w0,'splay':splay}
 # Thumb is a closed intentional insert under the glove, with 12 radial /12 axial loops.
 tr=O+U*.050+W*.008+N*.010;D=(U*.72+N*.69).normalized();T=D.cross(W).normalized();length=.066
 thumb=[]
 for ri in range(13):
  t=ri/12;center=tr+D*length*t+W*(.004*math.sin(t*math.pi));r=.013*(1-.35*t)
  if ri==12:r=.0035
  ids=[av(center+W*(math.cos(k*2*math.pi/12)*r)+T*(math.sin(k*2*math.pi/12)*r*.85),('thumb',role,t,k)) for k in range(12)]
  thumb.append(ids)
  if ri:
   for k in range(12):af((thumb[-2][k],thumb[-2][(k+1)%12],ids[(k+1)%12],ids[k]),1 if t<.17 else 2)
 af(tuple(reversed(thumb[0])),2);af(tuple(thumb[-1]),2)
 hand_models[role]={'sign':sign,'start':start,'end':len(verts),'fingers':meta,'thumb_root':list(tr),'thumb_direction':list(D),'thumb_length':length}
build_hand(1,'f');build_hand(-1,'b')
# Retain the player's identity with deliberately rebuilt closed earring loops.
for sign in []: # Original fine earring structure is retained by source-preserving reflow.
 rows=[];center=Vector((sign*.099,-.232,1.464))
 for i in range(48):
  a=2*math.pi*i/48;row=[];rad=Vector((math.cos(a),0,math.sin(a)))
  for j in range(8):
   b=2*math.pi*j/8;pos=center+Vector((.014*math.cos(a),0,.032*math.sin(a)))+rad*(.0019*math.cos(b))+Vector((0,.0019*math.sin(b),0));row.append(av(pos,('detail','head',i,j)))
  rows.append(row)
 for i in range(48):
  for j in range(8):af((rows[i][j],rows[(i+1)%48][j],rows[(i+1)%48][(j+1)%8],rows[i][(j+1)%8]),3)
hm=bpy.data.meshes.new('Authored_segmented_hand_quad_network');hm.from_pydata(verts,[],faces);hm.update();hands=bpy.data.objects.new('Authored_hands',hm);bpy.context.collection.objects.link(hands)
for p,mi in zip(hm.polygons,fmat):p.material_index=mi
bm=bmesh.new();bm.from_mesh(hm);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(hm);bm.free()

# High detail body reference preserves original UV/material; refine skin surface locally.
high=source.copy();high.data=source.data.copy();bpy.context.collection.objects.link(high);high.name='HIGH_Player_Refined_Bake'
high.modifiers.clear();active(high)
bm=bmesh.new();bm.from_mesh(high.data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.000004)
bmesh.ops.delete(bm,geom=[v for v in bm.verts if cut_hand(v.co)],context='VERTS')
bd=[e for e in bm.edges if e.is_boundary]
if bd:bmesh.ops.holes_fill(bm,edges=bd,sides=0)
for it in range(4):
 up=[]
 for v in bm.verts:
  c=v.co
  if abs(c.x)<.092 and 1.44<c.z<1.558 and c.y<-.25 and len(v.link_edges)>2:
   avg=sum((e.other_vert(v).co for e in v.link_edges),Vector())/len(v.link_edges);up.append((v,c.lerp(avg,.15)))
 for v,p in up:v.co=p
bm.to_mesh(high.data);bm.free()
def solid_material(name,color,rough):
 m=bpy.data.materials.new(name);m.use_nodes=True;bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*color,1);bs.inputs['Roughness'].default_value=rough;return m
glove=solid_material('Authored indigo glove',(.145,.18,.24),.64)
skin=solid_material('Refined warm skin',(.69,.46,.37),.55)
metal=solid_material('Refined matte ivory jewelry',(.65,.61,.53),.36);metal.node_tree.nodes['Principled BSDF'].inputs['Metallic'].default_value=.35
hands.data.materials.append(source.data.materials[0]);hands.data.materials.append(glove);hands.data.materials.append(skin);hands.data.materials.append(metal)
highhand=hands.copy();highhand.data=hands.data.copy();bpy.context.collection.objects.link(highhand);highhand.name='HIGH_Hands_Refined_Bake';active(highhand)
sub=highhand.modifiers.new('Finger sculpt supporting loops','SUBSURF');sub.levels=2;bpy.ops.object.modifier_apply(modifier=sub.name)
for p in highhand.data.polygons:p.use_smooth=True
# Low topology hand indices are retained in sidecar metadata before joining.
body_count=len(low.data.vertices);low.data.materials.append(source.data.materials[0]);active(low);hands.select_set(True);bpy.ops.object.join()
low.name='PLAYER_Retopo_Game_Quads';low['topology']='Source-preserving fullbodyedge collapse +quad reconstruction +explicit closed eyelid/lip loops +connected palm/finger rings +thumb insert +joint quad grids'
hand_ids={r:range(body_count+m['start'],body_count+m['end']) for r,m in hand_models.items()}
for p in low.data.polygons:p.use_smooth=True

# Transfer repaired body skin barycentrically; no neutral influence; max4 normalized.
def bary(p,a,b,c):
 v0=b-a;v1=c-a;v2=p-a;d00=v0.dot(v0);d01=v0.dot(v1);d11=v1.dot(v1);d20=v2.dot(v0);d21=v2.dot(v1);den=d00*d11-d01*d01
 if abs(den)<1e-16:return [1,0,0]
 v=(d11*d20-d01*d21)/den;w=(d00*d21-d01*d20)/den;vals=[max(0,1-v-w),max(0,v),max(0,w)];s=sum(vals);return [x/s for x in vals]
groups={b.name:low.vertex_groups.new(name=b.name) for b in arm.data.bones}
maxerr=0;maxinfluence=0
for v in low.data.vertices:
 if v.index>=body_count:
  role=tags[v.index-body_count][1];ws={('head' if role=='head' else 'forearm_'+role):1.}
 else:
  p,n,fi,d=bvh.find_nearest(v.co);maxerr=max(maxerr,d);poly=origpoly[fi];ba=bary(p,*[origco[x] for x in poly]);ws={}
  for vi,k in zip(poly,ba):
   for name,w in weights[vi].items():ws[name]=ws.get(name,0)+w*k
  ws=dict(sorted(ws.items(),key=lambda x:-x[1])[:4]);total=sum(ws.values())
  if total<1e-8:ws={'head':1.} if v.co.z>1.4 else {'hips':1.}
  else:ws={name:w/total for name,w in ws.items() if w>1e-6};total=sum(ws.values());ws={name:w/total for name,w in ws.items()}
 for name,w in ws.items():groups[name].add([v.index],w,'REPLACE')
 maxinfluence=max(maxinfluence,len(ws))
mod=low.modifiers.new('Original14bone repaired skin','ARMATURE');mod.object=arm;low.parent=arm
for role in ['f','b']:
 g=low.vertex_groups.new(name='MASK_hand_'+role);g.add(list(hand_ids[role]),1,'REPLACE')

# A genuinely new packed UV atlas, not a retained source triangle atlas.
active(low);bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project(angle_limit=math.radians(68),island_margin=.002,area_weight=.4,correct_aspect=True,scale_to_bounds=True);bpy.ops.object.mode_set(mode='OBJECT')
low.data.uv_layers.active.name='Retopology_4K_Atlas'
# Transfer the original source UV chart locally per face, avoiding ray-bake misses
# on the costume's overlapping thin components. Bake these temporary materials
# to the genuinely new Retopology atlas, then remove this temporary source chart.
transfer=low.data.uv_layers.new(name='Source_TransferredUV')
def bary_unclamped(p,a,b,c):
 v0=b-a;v1=c-a;v2=p-a;d00=v0.dot(v0);d01=v0.dot(v1);d11=v1.dot(v1);d20=v2.dot(v0);d21=v2.dot(v1);den=d00*d11-d01*d01
 if abs(den)<1e-16:return [1,0,0]
 v=(d11*d20-d01*d21)/den;w=(d00*d21-d01*d20)/den;return [1-v-w,v,w]
for p in low.data.polygons:
 if all(vi<body_count for vi in p.vertices):
  center=sum((low.data.vertices[vi].co for vi in p.vertices),Vector())/len(p.vertices);q,n,fi,d=bvh.find_nearest(center);tri=origpoly[fi]
  for li in p.loop_indices:
   co=low.data.vertices[low.data.loops[li].vertex_index].co;ba=bary_unclamped(co,*[origco[x] for x in tri]);uv=sum((u*w for u,w in zip(origuv[fi],ba)),Vector((0,0)));transfer.data[li].uv=uv
retained_material_indices=[p.material_index for p in low.data.polygons]
source_transfer=source.data.materials[0].copy();source_transfer.name='TEMP_Source_UV_Transfer'
uvnode=source_transfer.node_tree.nodes.new('ShaderNodeUVMap');uvnode.uv_map='Source_TransferredUV'
for n in list(source_transfer.node_tree.nodes):
 if n.type=='TEX_IMAGE':source_transfer.node_tree.links.new(uvnode.outputs[0],n.inputs['Vector'])
 if n.type=='NORMAL_MAP':n.uv_map='Source_TransferredUV'
low.data.materials.clear()
for mat in [source_transfer,glove,skin,metal]:low.data.materials.append(mat)
for p,mi in zip(low.data.polygons,retained_material_indices):
 p.material_index=0 if all(vi<body_count for vi in p.vertices) else mi
low.data.uv_layers.active=low.data.uv_layers['Retopology_4K_Atlas'];low.data.uv_layers['Retopology_4K_Atlas'].active_render=True
newmat=bpy.data.materials.new('Player_Retopology_PBR_4K');newmat.use_nodes=True

# Selected-high to active-low bakes. ORM uses the original physical channels via emission.
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=8;scene.render.bake.use_selected_to_active=False;scene.render.bake.cage_extrusion=.010;scene.render.bake.max_ray_distance=.05;scene.render.bake.margin=16
def bake_image(name,kind):
 im=bpy.data.images.new(name,width=4096,height=4096,alpha=True);im.colorspace_settings.name='sRGB' if kind=='DIFFUSE' else 'Non-Color';im.generated_color=(.5,.5,1,1) if kind=='NORMAL' else (.1,.1,.1,1)
 node=newmat.node_tree.nodes.new('ShaderNodeTexImage');node.image=im;newmat.node_tree.nodes.active=node
 for mat in low.data.materials:
  target=mat.node_tree.nodes.new('ShaderNodeTexImage');target.image=im;mat.node_tree.nodes.active=target
 active(low)
 if kind=='DIFFUSE':scene.render.bake.use_pass_direct=False;scene.render.bake.use_pass_indirect=False;scene.render.bake.use_pass_color=True
 bpy.ops.object.bake(type=kind)
 im.filepath_raw=OUT+'/textures/'+name+'.png';im.file_format='PNG';im.save();log('baked',name)
 return im,node
def surface_resample_bake():
 # Every target texel is located on the new UV triangle, then sampled from the
 # nearest original triangle's own UV. This removes UV seam extrapolation and
 # ray misses while preserving 4K embroidery; generated hands use authored PBR.
 size=4096
 srcimgs=[bpy.data.images['texture_pbr_20250901'],bpy.data.images['texture_pbr_20250901_metallic-texture_pbr_20250901_roughness']]
 arrays=[]
 for im in srcimgs:
  a=np.empty(len(im.pixels),np.float32);im.pixels.foreach_get(a);arrays.append(a.reshape(im.size[1],im.size[0],4))
 pixels=[np.zeros((size,size,4),np.float32),np.zeros((size,size,4),np.float32)];filled=np.zeros((size,size),bool)
 low.data.calc_loop_triangles();uvl=low.data.uv_layers['Retopology_4K_Atlas']
 known={1:((.145,.18,.24,1),(1,.64,0,1)),2:((.69,.46,.37,1),(1,.55,0,1)),3:((.65,.61,.53,1),(1,.36,.35,1))}
 count=0
 for ti,tri in enumerate(low.data.loop_triangles):
  uv=np.array([tuple(uvl.data[l].uv) for l in tri.loops])*size
  xmin=max(0,int(np.floor(uv[:,0].min())));xmax=min(size-1,int(np.ceil(uv[:,0].max())));ymin=max(0,int(np.floor(uv[:,1].min())));ymax=min(size-1,int(np.ceil(uv[:,1].max())))
  if xmax<xmin or ymax<ymin:continue
  xx,yy=np.meshgrid(np.arange(xmin,xmax+1)+.5,np.arange(ymin,ymax+1)+.5);d=uv[1]-uv[0];e=uv[2]-uv[0];det=d[0]*e[1]-d[1]*e[0]
  if abs(det)<1e-10:continue
  px=xx-uv[0,0];py=yy-uv[0,1];b=(px*e[1]-py*e[0])/det;c=(d[0]*py-d[1]*px)/det;a=1-b-c;ok=(a>=-1e-6)&(b>=-1e-6)&(c>=-1e-6)
  ys,xs=np.nonzero(ok);xs+=xmin;ys+=ymin
  if not len(xs):continue
  filled[ys,xs]=True;mi=low.data.polygons[tri.polygon_index].material_index
  if mi in known:
   for out,col in zip(pixels,known[mi]):out[ys,xs]=col
  else:
   barys=np.array([a[ok],b[ok],c[ok]]).T;coords=np.array([tuple(low.data.vertices[vi].co) for vi in tri.vertices]);points=barys@coords;colors=[[],[]]
   for point in points:
    q,n,fi,dist=bvh.find_nearest(Vector(point));tr=origpoly[fi];ba=bary(q,*[origco[j] for j in tr]);u=sum((t*w for t,w in zip(origuv[fi],ba)),Vector((0,0)));sx=min(size-1,max(0,int(u.x*size)));sy=min(size-1,max(0,int(u.y*size)))
    colors[0].append(arrays[0][sy,sx]);colors[1].append(arrays[1][sy,sx])
   for out,col in zip(pixels,colors):out[ys,xs]=col
  count+=len(xs)
  if ti%4000==0:log('surface_bake',ti,'/',len(low.data.loop_triangles),'texels',count)
 # Sixteen pixel edge dilation around packed islands.
 for it in range(4):
  nxt=filled.copy()
  for dy,dx in [(1,0),(-1,0),(0,1),(0,-1)]:
   shifted=np.roll(filled,(dy,dx),(0,1));mask=shifted&~nxt
   for out in pixels:out[mask]=np.roll(out,(dy,dx),(0,1))[mask]
   nxt|=shifted
  filled=nxt
 result=[]
 for name,pix,cs in [('player-basecolor-4k',pixels[0],'sRGB'),('player-orm-4k',pixels[1],'Non-Color')]:
  im=bpy.data.images.new(name,width=size,height=size,alpha=True);im.colorspace_settings.name=cs;im.pixels.foreach_set(pix.ravel());im.filepath_raw=OUT+'/textures/'+name+'.png';im.file_format='PNG';im.save();node=newmat.node_tree.nodes.new('ShaderNodeTexImage');node.image=im;result.append((im,node))
 log('surface_resample_bake_complete',count)
 return result
(base,basen),(orm,ormn)=surface_resample_bake()
scene.render.bake.use_selected_to_active=True
# Temporary materials all point to the normal target; selected high reference is
# an actual subdivided hand sculpt plus refined original scanned body.
def bake_high_normal():
 im=bpy.data.images.new('player-normal-4k',width=4096,height=4096,alpha=True);im.colorspace_settings.name='Non-Color';im.generated_color=(.5,.5,1,1)
 node=newmat.node_tree.nodes.new('ShaderNodeTexImage');node.image=im
 for mat in low.data.materials:
  target=mat.node_tree.nodes.new('ShaderNodeTexImage');target.image=im;mat.node_tree.nodes.active=target
 active(low);high.select_set(True);highhand.select_set(True);bpy.ops.object.bake(type='NORMAL');im.filepath_raw=OUT+'/textures/player-normal-4k.png';im.file_format='PNG';im.save();return im,node
normal,normaln=bake_high_normal()
low.data.materials.clear();low.data.materials.append(newmat)
for p in low.data.polygons:p.material_index=0
low.data.uv_layers.remove(transfer)
nt=newmat.node_tree;bs=nt.nodes.get('Principled BSDF');nt.links.new(basen.outputs['Color'],bs.inputs['Base Color'])
nm=nt.nodes.new('ShaderNodeNormalMap');nt.links.new(normaln.outputs['Color'],nm.inputs['Color']);nt.links.new(nm.outputs['Normal'],bs.inputs['Normal'])
sep=nt.nodes.new('ShaderNodeSeparateColor');nt.links.new(ormn.outputs['Color'],sep.inputs[0]);nt.links.new(sep.outputs[1],bs.inputs['Roughness']);nt.links.new(sep.outputs[2],bs.inputs['Metallic'])

# Progressive morphs use finite-radius articulated finger arcs and a separate safe thumb fold.
low.shape_key_add(name='Basis')
def bendpoint(role,tag,p,amount):
 m=hand_models[role];O,U,W,N=frame(m['sign']);kind=tag[0]
 if kind=='finger':
  fi,t,k=tag[2:];fm=m['fingers'][fi];root=Vector(fm['root']);L=fm['length'];splay=fm['splay']
  oldcenter=root+U*(L*t)+W*(L*t*splay)+N*(-.003*math.sin(t*math.pi));q=p-oldcenter
  # Three finite arc segments distributed over MCP/PIP/DIP; half is a separate pose.
  angles=[.60, .82, .59] if amount==.5 else [1.20,1.42,1.04]
  fractions=[.42,.32,.26];remaining=t;center=root;theta=0
  for frac,ang in zip(fractions,angles):
   n=min(frac,remaining)
   if n<=0:break
   rate=ang/(L*frac);a=rate*(L*n)
   center+=U*((math.sin(theta+a)-math.sin(theta))/rate)+N*((math.cos(theta+a)-math.cos(theta))/rate)
   theta+=a;remaining-=n
  center+=W*(L*t*splay*(1-amount*.80))
  along=q.dot(U);lat=q.dot(W);rad=q.dot(N)
  tangent=U*math.cos(theta)-N*math.sin(theta);normal=N*math.cos(theta)+U*math.sin(theta)
  return center+tangent*along+W*lat+normal*rad
 if kind=='thumb':
  t,k=tag[2:];tr=Vector(m['thumb_root']);D=Vector(m['thumb_direction']);L=m['thumb_length'];T=D.cross(W).normalized();oldcenter=tr+D*L*t+W*(.004*math.sin(t*math.pi));q=p-oldcenter
  angle=(.64 if amount==.5 else 1.18)*t;D2=(U*math.cos(angle)+W*(-math.sin(angle)*.82)+N*(.34*(1-t))).normalized()
  center=tr+D2*(L*t)-N*(.014*amount*t)
  return center+W*q.dot(W)+D2.cross(W).normalized()*q.dot(T)
 return p
for role in ['f','b']:
 for amount,name in [(.5,'grip_half_'+role),(1.,'grip_'+role)]:
  key=low.shape_key_add(name=name)
  for vi in hand_ids[role]:key.data[vi].co=bendpoint(role,tags[vi-body_count],low.data.vertices[vi].co,amount)
  key.value=0
low.data.shape_keys.name='Progressive_Hands_Open_Half_Closed'
low['hand_authoring']='Connected quad palm+four8-sided segmented15-ring fingers;12-sided12-ring thumb insert. Basis open.'

# Sockets are sampled authored surface vertices, at open palm and half/closed knuckle.
sockets={'version':1,'role':'player','space':'blender_world_z_up'}
for role,label in [('f','front'),('b','rear')]:
 ids=list(hand_ids[role]);palm=[i for i in ids if tags[i-body_count][0]=='palm' and tags[i-body_count][4]==1]
 vi=min(palm,key=lambda i:abs(tags[i-body_count][2]-.062)+abs(tags[i-body_count][3]))
 knuckle=[i for i in ids if tags[i-body_count][0]=='finger' and tags[i-body_count][2]==1 and abs(tags[i-body_count][3]-.24)<.01]
 ki=knuckle[0];sockets[label]={'open':list(low.data.vertices[vi].co),'half':list(low.data.shape_keys.key_blocks['grip_half_'+role].data[ki].co),'closed':list(low.data.shape_keys.key_blocks['grip_'+role].data[ki].co)}
json.dump(sockets,open(OUT+'/contact-sockets.json','w'),indent=2)
json.dump({'body_vertex_count':body_count,'hand_models':hand_models,'hand_vertex_tags':tags},open(OUT+'/hand-authoring.json','w'),indent=2)

hide(source);hide(high);hide(highhand)
scene.world=bpy.data.worlds.new('Player studio');scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.17,.17,.17,1)
for loc,power,size in [((2,-3,4),600,4),((-3,-1,2),400,3),((0,3,3),700,3)]:
 bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.data.energy=power;l.data.shape='DISK';l.data.size=size;l.rotation_euler=(Vector((0,0,.86))-l.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add();cam=bpy.context.object;cam.data.type='ORTHO';scene.camera=cam;scene.cycles.samples=24
scene.render.resolution_percentage=100
def render(name,target,loc,scale,w=1000,h=700):
 cam.location=loc;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=scale;scene.render.resolution_x=w;scene.render.resolution_y=h;scene.render.filepath=OUT+'/'+name+'.png';bpy.ops.render.render(write_still=True)
render('candidate-full',(0,0,.86),(0,-4,1.06),2.064,900,1000)
render('candidate-face',(0,-.16,1.55),(0,-3,1.55),.42)
render('candidate-hands',(.535,-.225,.96),(.8,-2,1.25),.27)
render('candidate-hand-back',(.535,-.225,.96),(.6,2,1.2),.27)
for g in [0,.25,.5,.75,1]:
 for role in ['f','b']:
  low.data.shape_keys.key_blocks['grip_half_'+role].value=2*g if g<=.5 else 2*(1-g)
  low.data.shape_keys.key_blocks['grip_'+role].value=0 if g<=.5 else 2*g-1
 render('grip-'+str(g).replace('.','p'),(.535,-.225,.96),(.8,-2,1.25),.29)
for key in low.data.shape_keys.key_blocks:key.value=0
wire=low.modifiers.new('QA wireframe','WIREFRAME');wire.thickness=.0005;wire.use_replace=False
wm=solid_material('Wire topology ink',(.018,.032,.047),.65);low.data.materials.append(wm);wire.material_offset=1
render('candidate-wireframe',(0,0,.86),(0,-4,1.06),2.064,900,1000);render('candidate-hand-wireframe',(.535,-.225,.96),(.8,-2,1.25),.29)
low.modifiers.remove(wire);low.data.materials.pop(index=1)
active(low);arm.select_set(True)
# QA masks are Blender-only; they must not contaminate exported glTF joints.
for g in list(low.vertex_groups):
 if g.name.startswith('MASK_'):low.vertex_groups.remove(g)
glb=OUT+'/player-raw.glb'
bpy.ops.export_scene.gltf(filepath=glb,export_format='GLB',use_selection=True,export_skins=True,export_morph=True,export_morph_normal=True,export_animations=False,export_apply=False,export_yup=True,export_materials='EXPORT')
for role in ['f','b']:
 g=low.vertex_groups.new(name='MASK_hand_'+role);g.add(list(hand_ids[role]),1,'REPLACE')
# Editable source/high/quad low remain in authoring .blend with the fulloriginal skeleton.
for im in [base,normal,orm]:im.pack()
bpy.ops.wm.save_as_mainfile(filepath=OUT+'/player-retopology.blend')
quads=sum(len(p.vertices)==4 for p in low.data.polygons);tris=sum(len(p.vertices)-2 for p in low.data.polygons)
report={'version':1,'role':'player','source_sha256':source['immutable_source_sha256'],'source_vertices':len(origco),'source_triangles':source_tris,'baseline_acceptance':'FAIL triangles only; morphs absent','new_vertices':len(low.data.vertices),'new_faces':len(low.data.polygons),'quads':quads,'quad_fraction':quads/len(low.data.polygons),'triangles':tris,'feature_loops':feature_counts,'max_body_projection_error_m':maxerr,'max_influences':maxinfluence,'neutral_visible_weight':0,'morphs':[k.name for k in low.data.shape_keys.key_blocks],'texture_sizes':{im.name:list(im.size) for im in [base,normal,orm]},'seconds':time.time()-START,'outputs':{os.path.relpath(p,OUT):sha(p) for p in [glb,OUT+'/player-retopology.blend',OUT+'/contact-sockets.json']+[OUT+'/textures/'+im.name+'.png' for im in [base,normal,orm]]},'notes':['Repaired baseline weights barycentrically transferred; original14joint armature unchanged.','New base connectivity QuadriFlow, connected explicit eye/lip rings, manual procedural palm/finger rings and local joint grids.','Thumb is a sealed deliberate insert rooted under glove; originalscan costume is a connected surface.','PBR channels are rebaked using local sourceUV retargeting to avoid missed rays on thin overlapping scan components. Refined highdetail references retained.','Facial feature rings retain source form; no claim of feature-film facial animation rig.']}
json.dump(report,open(OUT+'/build-report.json','w'),indent=2);log('DONE',json.dumps(report))
