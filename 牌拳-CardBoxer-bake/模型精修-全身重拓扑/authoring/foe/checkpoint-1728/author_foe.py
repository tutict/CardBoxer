"""Reproducible foe retopology, connected glove loops, progressive shapes and PBR bake.
Run with the owned Blender 5.2 background process; immutable baseline is never saved.
"""
import bpy, bmesh, math, json, hashlib, os, time, sys
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'authoring/foe'; OUT.mkdir(parents=True,exist_ok=True)
TEX=OUT/'textures'; TEX.mkdir(exist_ok=True)
START=time.time(); REPORT={'version':1,'role':'foe','blender':bpy.app.version_string}
def log(s): print('FOE',s,flush=True)
def active(o):
 bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
def stats(o):
 bm=bmesh.new();bm.from_mesh(o.data)
 unseen=set(bm.verts);components=[]
 while unseen:
  todo=[unseen.pop()];n=0
  while todo:
   v=todo.pop();n+=1
   for e in v.link_edges:
    w=e.other_vert(v)
    if w in unseen:unseen.remove(w);todo.append(w)
  components.append(n)
 r={'vertices':len(bm.verts),'edges':len(bm.edges),'polygons':len(bm.faces),'triangles':sum(len(f.verts)-2 for f in bm.faces),'quads':sum(len(f.verts)==4 for f in bm.faces),'boundary_edges':sum(e.is_boundary for e in bm.edges),'nonmanifold_edges':sum(not e.is_manifold for e in bm.edges),'component_count':len(components),'components':sorted(components,reverse=True)[:24]}
 bm.free();return r
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def material(name,color,metal,rough):
 m=bpy.data.materials.new(name);m.use_nodes=True;n=m.node_tree.nodes.get('Principled BSDF');n.inputs['Base Color'].default_value=(*color,1);n.inputs['Metallic'].default_value=metal;n.inputs['Roughness'].default_value=rough
 return m
def cut_hands(o):
 bm=bmesh.new();bm.from_mesh(o.data)
 kill=[v for v in bm.verts if abs(v.co.x)>.395 and .62<v.co.z<.902 and v.co.y<-.07]
 bmesh.ops.delete(bm,geom=kill,context='VERTS')
 bmesh.ops.delete(bm,geom=[v for v in bm.verts if not v.link_faces],context='VERTS')
 bm.to_mesh(o.data);bm.free();o.data.update()
def boundary_loops(mesh):
 bm=bmesh.new();bm.from_mesh(mesh);bm.verts.ensure_lookup_table();bm.verts.index_update();edges=set(e for e in bm.edges if e.is_boundary);loops=[]
 while edges:
  e=edges.pop();seq=[e.verts[0],e.verts[1]];cur=seq[-1]
  while cur!=seq[0]:
   nxt=next((q for q in cur.link_edges if q in edges),None)
   if nxt is None:break
   edges.remove(nxt);cur=nxt.other_vert(cur)
   if cur!=seq[0]:seq.append(cur)
  loops.append([v.index for v in seq])
 bm.free();return loops
def orient(mesh):
 bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free();mesh.update()
def cleanup_body(low):
 bm=bmesh.new();bm.from_mesh(low.data);unseen=set(bm.verts);drop=[]
 while unseen:
  component=[];todo=[unseen.pop()]
  while todo:
   v=todo.pop();component.append(v)
   for e in v.link_edges:
    w=e.other_vert(v)
    if w in unseen:unseen.remove(w);todo.append(w)
  if len(component)<80:drop.extend(component)
 if drop:bmesh.ops.delete(bm,geom=drop,context='VERTS')
 boundary=[e for e in bm.edges if e.is_boundary]
 if boundary:bmesh.ops.holes_fill(bm,edges=boundary,sides=0)
 bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(low.data);bm.free();low.data.update();low.data.validate(verbose=True)
 # Project new vertices, not source indices, back onto the immutable silhouette.
 tree=BVHTree.FromPolygons([v.co.copy() for v in SOURCE.data.vertices],[list(p.vertices) for p in SOURCE.data.polygons])
 for v in low.data.vertices:
  nearest=tree.find_nearest(v.co)
  if nearest and nearest[0] is not None:v.co=nearest[0]
 low.data.update()
 log('project samples '+str([list(low.data.vertices[i].co) for i in [0,100,1000,20000]])+' source '+str([list(SOURCE.data.vertices[i].co) for i in [0,100,1000]]))
def clean_cut_fragments(low):
 bm=bmesh.new();bm.from_mesh(low.data);unseen=set(bm.verts);components=[]
 while unseen:
  todo=[unseen.pop()];component=[]
  while todo:
   v=todo.pop();component.append(v)
   for e in v.link_edges:
    w=e.other_vert(v)
    if w in unseen:unseen.remove(w);todo.append(w)
  components.append(component)
 largest=max(components,key=len);drop=[v for component in components if component is not largest for v in component]
 if drop:bmesh.ops.delete(bm,geom=drop,context='VERTS')
 bmesh.ops.delete(bm,geom=[e for e in bm.edges if not e.link_faces],context='EDGES');bm.to_mesh(low.data);bm.free();low.data.update()
 loops=boundary_loops(low.data)
 keep=[]
 for sign in [1,-1]:
  candidates=[l for l in loops if sum(low.data.vertices[i].co.x for i in l)*sign>0]
  if candidates:keep.append(max(candidates,key=len))
 bm=bmesh.new();bm.from_mesh(low.data);bm.verts.ensure_lookup_table();bm.verts.index_update()
 for loop in loops:
  if loop in keep:continue
  seq=list(dict.fromkeys(loop))
  if len(seq)>=3:
   try:bm.faces.new([bm.verts[i] for i in seq])
   except ValueError:pass
 bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(low.data);bm.free();low.data.update()
def refine_mask_and_edges(low):
 tree=BVHTree.FromPolygons([v.co.copy() for v in SOURCE.data.vertices],[list(p.vertices) for p in SOURCE.data.polygons]);verts=[v.co.copy() for v in low.data.vertices];faces=[list(p.vertices) for p in low.data.polygons];mats=[p.material_index for p in low.data.polygons];begin=len(verts)
 def trace_ring(cx,cz,rx,rz,thickness,steps=40):
  loops=[]
  for j in range(steps):
   a=j*math.tau/steps;x=cx+rx*math.cos(a);z=cz+rz*math.sin(a);hit=tree.ray_cast(Vector((x,-1,z)),Vector((0,1,0)))
   if hit[0] is None:return
   center=hit[0]+Vector((0,-thickness*.6,0));radial=Vector((math.cos(a),0,math.sin(a)));ring=[]
   for k in range(6):
    b=k*math.tau/6;p=center+radial*(thickness*math.cos(b))+Vector((0,-thickness*math.sin(b),0));ring.append(len(verts));verts.append(p)
   loops.append(ring)
  for j in range(steps):
   for k in range(6):faces.append([loops[j][k],loops[(j+1)%steps][k],loops[(j+1)%steps][(k+1)%6],loops[j][(k+1)%6]]);mats.append(2)
 # Supported circular gasket and breather rim loops sit on the original visible surface.
 for x in [-.049,.049]:trace_ring(x,1.585,.022,.022,.0016)
 trace_ring(0,1.510,.026,.050,.0012)
 mesh=bpy.data.meshes.new('Foe_ControlledMaskRims');mesh.from_pydata(verts,[],faces);mesh.update();low.data=mesh
 for m in [SOURCE.data.materials[0],LEATHER,METAL]:mesh.materials.append(m)
 for p,mi in zip(mesh.polygons,mats):p.material_index=mi;p.use_smooth=True
 orient(mesh);REPORT['surface_detail_vertex_range']=[begin,len(verts)];REPORT['mask_refinement']='two 40x6 supported goggle gasket rings and 40x6 breather perimeter, ray conformed to immutable mask silhouette'
def join_list(obs,name):
 bpy.ops.object.select_all(action='DESELECT')
 for o in obs:o.select_set(True)
 bpy.context.view_layer.objects.active=obs[0];bpy.ops.object.join();o=bpy.context.object;o.name=name;return o
def zipper(a,b,faces):
 # Both cyclic boundaries ordered in the same direction; unequal ring counts allowed.
 i=j=0
 while i<len(a) or j<len(b):
  ti=(i+1)/len(a) if i<len(a) else 2;tj=(j+1)/len(b) if j<len(b) else 2
  if abs(ti-tj)<1e-8:faces.append([a[i%len(a)],a[(i+1)%len(a)],b[(j+1)%len(b)],b[j%len(b)]]);i+=1;j+=1
  elif ti<tj:faces.append([a[i%len(a)],a[(i+1)%len(a)],b[j%len(b)]]);i+=1
  else:faces.append([a[i%len(a)],b[(j+1)%len(b)],b[j%len(b)]]);j+=1
def build_gloves(low):
 verts=[v.co.copy() for v in low.data.vertices];faces=[list(p.vertices) for p in low.data.polygons];mats=[p.material_index for p in low.data.polygons]
 original_count=len(verts);meta=[];ranges={};newfaces=[];keys={k:[v.copy() for v in verts] for k in ['grip_half_f','grip_f','grip_half_b','grip_b']}
 loops=boundary_loops(low.data)
 log('loops '+str([(len(l),[sum(verts[i][j] for i in l)/len(l) for j in range(3)]) for l in loops]))
 for side,sign in [('f',1),('b',-1)]:
  loop=max((l for l in loops if sum(verts[i].x for i in l)*sign>0),key=len)
  center=sum((verts[i] for i in loop),Vector())/len(loop);cx=sign*.535;cy=-.191;z=.790
  log(f'{side} wrist loop {len(loop)} center {tuple(center)}')
  begin=len(verts);roots=[];finger_defs=[]
  def add(p):
   idx=len(verts);verts.append(Vector(p));
   for k in keys:keys[k].append(Vector(p))
   return idx
  def face(v,mi=1):faces.append(v);mats.append(mi)
  # Regularize the hidden gauntlet exit loop into an intentional smooth oval cuff.
  # The previous concave cut edge was topologically closed but made a folded fan.
  area=sum(verts[loop[j]].x*verts[loop[(j+1)%len(loop)]].y-verts[loop[(j+1)%len(loop)]].x*verts[loop[j]].y for j in range(len(loop)));direction=1 if area>0 else -1
  start=math.atan2(verts[loop[0]].y-center.y,verts[loop[0]].x-center.x)
  if REPORT.get('base_method')=='quadriflow':
   for j,ix in enumerate(loop):
    a=start+direction*j*math.tau/len(loop);p=Vector((center.x+.073*math.cos(a),center.y+.061*math.sin(a),.906));verts[ix]=p
    for k in keys:keys[k][ix]=p.copy()
  for fi in range(4):
   x=cx+(fi-1.5)*.026;ring=[]
   for a in range(8):
    t=a*math.tau/8;ring.append(add((x+.0108*math.cos(t),cy+.018*math.sin(t),z)))
   roots.append(ring)
  # Webbing quads between the four root holes, then a single outer palm boundary.
  for a,b in zip(roots,roots[1:]):
   face([a[0],a[1],b[3],b[4]]);face([a[7],a[0],b[4],b[5]])
  outer=[]
  for r in roots:outer.extend([r[3],r[2],r[1]])
  outer.extend([roots[-1][0]])
  for r in reversed(roots):outer.extend([r[7],r[6],r[5]])
  outer.append(roots[0][4])
  if sign<0:
   # Cross-section ordering is geometric, independent of role.
   pass
  previous=outer;palm_rings=[outer];palm_faces=[]
  for zz,width,depth in [(.808,.054,.028),(.842,.056,.033),(.875,.051,.031)]:
   ring=[]
   for ix in outer:
    p=verts[ix];xx=(p.x-cx)/.05;yy=(p.y-cy)/.018
    ring.append(add((cx+xx*width*(1-.06*abs(yy)),cy+yy*depth*math.sqrt(max(.35,1-.55*xx*xx)),zz)))
   strip=[]
   for j in range(len(ring)):strip.append(len(faces));face([previous[j],previous[(j+1)%len(ring)],ring[(j+1)%len(ring)],ring[j]])
   palm_faces.append(strip);palm_rings.append(ring);previous=ring
  # Match source wrist seam by cyclic nearest angular ordering.
  # Preserve mesh edge traversal. Angular sorting tears concave armor cuffs into spikes.
  candidates=[]
  for order in [loop,list(reversed(loop))]:
   for shift in range(len(order)):
    seq=order[shift:]+order[:shift];score=sum((verts[seq[int(j*len(seq)/len(previous))]]-verts[ix]).length_squared for j,ix in enumerate(previous));candidates.append((score,seq))
  loop=min(candidates,key=lambda q:q[0])[1]
  bridge=[];zipper(loop,previous,bridge)
  for f in bridge:face(f)
  # Thirteen cross-section loops/finger, preserving knuckle segmentation through bending.
  lengths=[.091,.110,.106,.088]
  for fi,root in enumerate(roots):
   rootpos=sum((verts[i] for i in root),Vector())/8;length=lengths[fi]
   def path(t,state):
    angles=[.10,.20,.32] if state==0 else ([.48,.95,1.38] if state==1 else [1.0,1.98,2.80])
    segment=min(2,int(t*3));p=rootpos.copy()
    for si in range(segment+1):
     fraction=1 if si<segment else (t*3-segment);L=length/3*fraction;p.y+=math.sin(angles[si])*L;p.z-=math.cos(angles[si])*L
    tangent=Vector((0,math.sin(angles[segment]),-math.cos(angles[segment])))
    return p,tangent
   prev=root
   for ri in range(1,14):
    t=ri/13;ring=[]
    radius=(1-.24*t)*(1+.09*math.cos(t*6*math.pi));rx=.0108*radius;ry=.018*(1-.34*t)+(.0015 if ri in [2,3,6,7,10,11] else 0)
    for ai in range(8):
     theta=ai*math.tau/8;p,tan=path(t,0);u=Vector((1,0,0));v=Vector((0,-tan.z,tan.y));p+=u*(rx*math.cos(theta))+v*(ry*math.sin(theta));ix=add(p);ring.append(ix)
     for st,k in [(1,'grip_half_'+side),(2,'grip_'+side)]:
      q,tan=path(t,st);v=Vector((0,-tan.z,tan.y));keys[k][ix]=q+u*(rx*math.cos(theta))+v*(ry*math.sin(theta))
    for j in range(8):face([prev[j],prev[(j+1)%8],ring[(j+1)%8],ring[j]],2 if j in [4,5,6,7] and ri in [2,3,6,7,10,11] else 1)
    prev=ring
   face(list(reversed(prev)))
  # Six-sided opening cut into the inner palm side, bridged to the eight-sided thumb root.
  mid=outer.index(roots[0][4] if sign>0 else roots[-1][0]);lo=palm_rings[1];up=palm_rings[2];N=len(outer)
  thumbhole=[lo[(mid-1)%N],lo[mid],lo[(mid+1)%N],up[(mid+1)%N],up[mid],up[(mid-1)%N]]
  remove=sorted([palm_faces[1][(mid-1)%N],palm_faces[1][mid]],reverse=True)
  for idx in remove:faces.pop(idx);mats.pop(idx)
  thumbbase=sum((verts[i] for i in thumbhole),Vector())/6;prev=None
  for ri in range(13):
   t=ri/12;ring=[]
   def thumb(state):
    if state==0:return thumbbase+Vector((-sign*.051*t,.008*math.sin(t*math.pi),-.057*t))
    if state==1:return thumbbase+Vector((-sign*.025*math.sin(t*math.pi*.7),.038*t,-.070*t))
    return thumbbase+Vector((sign*.019*t,.049*t,-.068*t))
   for ai in range(8):
    a=ai*math.tau/8
    def thumb_delta(state):
     eps=.001;tan=(thumb(state) if t>=1 else thumb(state))-thumbbase
     if tan.length<1e-6:tan=Vector((-sign*.051,0,-.057))
     tan.normalize();u=Vector((0,1,0));v=tan.cross(u).normalized();return (u*(.015*math.cos(a))+v*(.014*math.sin(a)))*(1-.40*t)
    delta=thumb_delta(0);ix=add(thumb(0)+delta);ring.append(ix)
    for st,k in [(1,'grip_half_'+side),(2,'grip_'+side)]:keys[k][ix]=thumb(st)+thumb_delta(st) if ri else thumb(0)+delta
   if prev:
    for j in range(8):face([prev[j],prev[(j+1)%8],ring[(j+1)%8],ring[j]])
   else:
    candidates=[]
    for order in [thumbhole,list(reversed(thumbhole))]:
     for shift in range(len(order)):
      seq=order[shift:]+order[:shift];score=sum((verts[seq[int(j*len(seq)/len(ring))]]-verts[ix]).length_squared for j,ix in enumerate(ring));candidates.append((score,seq))
    bridge=[];zipper(min(candidates,key=lambda q:q[0])[1],ring,bridge)
    for f in bridge:face(f)
   prev=ring
  face(list(reversed(prev)));ranges[side]=[begin,len(verts)]
  # Three supported rings around a dorsal hand armor plaque; separate enclosed plate.
  rings=[]
  for yy,w,h in [(cy-.034,.047,.029),(cy-.038,.046,.028),(cy-.0385,.044,.026)]:
   rr=[]
   for corner,(sx,sz) in enumerate([(1,1),(-1,1),(-1,-1),(1,-1)]):
    for step in range(4):
     a=corner*math.pi/2+step*math.pi/6;p=(sx*(w-.008)+.008*math.cos(a),sz*(h-.008)+.008*math.sin(a));rr.append(add((cx+p[0],yy,.842+p[1])))
   rings.append(rr)
  face(list(reversed(rings[0])),2)
  for a,b in zip(rings,rings[1:]):
   for j in range(len(a)):face([a[j],a[(j+1)%len(a)],b[(j+1)%len(a)],b[j]],2)
  face(rings[-1],2)
  # Four flush rivets retain the plated glove's industrial construction cues.
  for dx,dz in [(-.032,-.017),(.032,-.017),(-.032,.017),(.032,.017)]:
   ctr=Vector((cx+dx,cy-.042,.842+dz));radius=.0027;rows=[]
   for lat in [1,2,3]:
    rr=[];phi=lat*math.pi/4
    for j in range(8):
     a=j*math.tau/8;rr.append(add(ctr+Vector((radius*math.sin(phi)*math.cos(a),radius*math.sin(phi)*math.sin(a),radius*math.cos(phi)))))
    rows.append(rr)
   north=add(ctr+Vector((0,0,radius)));south=add(ctr-Vector((0,0,radius)))
   for j in range(8):face([north,rows[0][j],rows[0][(j+1)%8]],2);face([south,rows[-1][(j+1)%8],rows[-1][j]],2)
   for a,b in zip(rows,rows[1:]):
    for j in range(8):face([a[j],b[j],b[(j+1)%8],a[(j+1)%8]],2)
 mesh=bpy.data.meshes.new('Foe_Editable_QuadBody_and_GloveLoops');mesh.from_pydata(verts,[],faces);mesh.update();low.data=mesh
 for m in [SOURCE.data.materials[0],LEATHER,METAL]:mesh.materials.append(m)
 for p,mi in zip(mesh.polygons,mats):p.material_index=mi;p.use_smooth=True
 orient(mesh)
 REPORT['hand_vertex_ranges']=ranges;REPORT['body_vertices_before_hands']=original_count
 return keys,ranges
def transfer_skin(low,source,ranges):
 source.data.calc_loop_triangles();tris=list(source.data.loop_triangles);coords=[v.co.copy() for v in source.data.vertices];tree=BVHTree.FromPolygons(coords,[list(t.vertices) for t in tris],all_triangles=True)
 for g in list(low.vertex_groups):low.vertex_groups.remove(g)
 names=[g.name for g in source.vertex_groups]
 for n in names:low.vertex_groups.new(name=n)
 sw=[]
 for v in source.data.vertices:
  d={names[g.group]:g.weight for g in v.groups if names[g.group]!='neutral_bone'};sw.append(d)
 def bary(p,a,b,c):
  ab=b-a;ac=c-a;ap=p-a;d00=ab.dot(ab);d01=ab.dot(ac);d11=ac.dot(ac);den=d00*d11-d01*d01
  if abs(den)<1e-15:return [1,0,0]
  v=(d11*ap.dot(ab)-d01*ap.dot(ac))/den;w=(d00*ap.dot(ac)-d01*ap.dot(ab))/den;return [max(0,1-v-w),max(0,v),max(0,w)]
 group_lookup={g.name:g for g in low.vertex_groups};maxsum=0;repair=0
 for v in low.data.vertices:
  hand=next((s for s,(a,b) in ranges.items() if a<=v.index<b),None)
  if hand:d={'forearm_'+hand:1}
  else:
   p,no,idx,dist=tree.find_nearest(v.co);tri=tris[idx];vv=list(tri.vertices);weights=bary(p,*[coords[j] for j in vv]);d={}
   for j,w in zip(vv,weights):
    for n,q in sw[j].items():d[n]=d.get(n,0)+w*q
   # Correct source shoulder/head spill while retaining the original smooth joint skin.
   x,y,z=v.co
   if z>1.40 and abs(x)<.215:d={'head':1} if z>1.51 else {'neck':1};repair+=1
   elif z>1.29 and abs(x)<.17:d={'chest':1};repair+=1
   elif z<.14:d={'shin_f' if x>0 else 'shin_b':1};repair+=1
  d=dict(sorted(d.items(),key=lambda x:-x[1])[:4]);total=sum(d.values())
  if not total:d={'hips':1};total=1
  for n,w in d.items():group_lookup[n].add([v.index],w/total,'REPLACE')
  maxsum=max(maxsum,abs(sum(w/total for w in d.values())-1))
 REPORT['skin']={'max_influences':4,'normalization_error':maxsum,'neutral_influence_vertices':0,'spatial_repairs':repair,'method':'nearest triangle barycentric from baseline plus head/chest/sole repairs, gloves rigid to exact forearm group'}
 for m in list(low.modifiers):low.modifiers.remove(m)
 arm=low.modifiers.new('CanonicalBodySkin','ARMATURE');arm.object=ARM;low.parent=ARM
def make_high(low):
 high=SOURCE.copy();high.data=SOURCE.data.copy();bpy.context.collection.objects.link(high);high.name='Foe_Refined_High_Surface';high.hide_render=False;high.hide_set(False)
 for m in list(high.modifiers):high.modifiers.remove(m)
 bm=bmesh.new();bm.from_mesh(high.data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.000004);bm.to_mesh(high.data);bm.free();high.data.update();cut_hands(high);clean_cut_fragments(high)
 # High glove shell copies all replacement topology, allowing correct procedural bake.
 glove=low.copy();glove.data=low.data.copy();bpy.context.collection.objects.link(glove);glove.name='Foe_High_Glove_Panels'
 for m in list(glove.modifiers):glove.modifiers.remove(m)
 bm=bmesh.new();bm.from_mesh(glove.data);bm.verts.ensure_lookup_table();bm.verts.index_update();bmesh.ops.delete(bm,geom=[f for f in bm.faces if all(v.index<REPORT['body_vertices_before_hands'] for v in f.verts)],context='FACES');bmesh.ops.delete(bm,geom=[v for v in bm.verts if not v.link_faces],context='VERTS');bm.to_mesh(glove.data);bm.free()
 detail=low.copy();detail.data=low.data.copy();bpy.context.collection.objects.link(detail);detail.name='Foe_High_Controlled_Mask_Edges'
 for m in list(detail.modifiers):detail.modifiers.remove(m)
 a,b=REPORT['surface_detail_vertex_range'];bm=bmesh.new();bm.from_mesh(detail.data);bm.verts.ensure_lookup_table();bm.verts.index_update();bmesh.ops.delete(bm,geom=[v for v in bm.verts if not a<=v.index<b],context='VERTS');bm.to_mesh(detail.data);bm.free()
 return [high,glove,detail]
def atlas(low):
 active(low);bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project(angle_limit=math.radians(58),island_margin=.003,area_weight=.5);bpy.ops.object.mode_set(mode='OBJECT');low.data.uv_layers.active.name='Foe_4K_Atlas'
 REPORT['uv']={'name':'Foe_4K_Atlas','new_atlas':True,'method':'angle islands, .003 island margin, area weighted','runtime_channel':0,'uv_layers':len(low.data.uv_layers),'normal_basis':'tangent space UV0'}
 assert len(low.data.uv_layers)==1
def crystal_facets(low,high):
 import numpy as np
 source_mat=SOURCE.data.materials[0];bs=source_mat.node_tree.nodes.get('Principled BSDF');node=bs.inputs['Base Color'].links[0].from_node
 if node.type!='TEX_IMAGE':return
 image=node.image;pixels=np.empty(len(image.pixels),dtype=np.float32);image.pixels.foreach_get(pixels);W,H=image.size;pixels=pixels.reshape(H,W,4)
 SOURCE.data.calc_loop_triangles();tris=list(SOURCE.data.loop_triangles);tree=BVHTree.FromPolygons([v.co.copy() for v in SOURCE.data.vertices],[list(t.vertices) for t in tris],all_triangles=True);uv=SOURCE.data.uv_layers.active.data
 def cyan(loops,layer=uv):
  coords=[layer[i].uv.copy() for i in loops];u=sum(p.x for p in coords)/len(coords);v=sum(p.y for p in coords)/len(coords);r,g,b=pixels[min(H-1,max(0,int(v*H))),min(W-1,max(0,int(u*W))),:3];return b>r*1.30 and g>r*1.25 and b>.10
 selected=set();count=0
 for p in low.data.polygons:
  center=sum((low.data.vertices[i].co for i in p.vertices),Vector())/len(p.vertices)
  if abs(center.x)<.27 or center.z<1.39:continue
  hit=tree.find_nearest(center)
  if hit[0] is not None and cyan(tris[hit[2]].loops):p.use_smooth=False;selected.update(p.vertices);count+=1
 for p in high.data.polygons:
  c=p.center
  if abs(c.x)>.27 and c.z>1.39 and cyan(p.loop_indices,high.data.uv_layers.active.data):p.use_smooth=False
 sharp=low.data.attributes.get('sharp_edge') or low.data.attributes.new('sharp_edge','BOOLEAN','EDGE')
 for e in low.data.edges:
  if all(i in selected for i in e.vertices):sharp.data[e.index].value=True
 if selected:g=low.vertex_groups.new(name='AUTHOR_cyan_crystal_facets');g.add(sorted(selected),1,'REPLACE')
 REPORT['crystal_refinement']={'cyan_faces_with_flat_facets':count,'masked_vertices':len(selected),'method':'source-albedo cyan mask, new low quad surfaces with explicit sharp-edge attributes and flat high bake facets'}
def bake(low,highs):
 scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=8;scene.render.bake.use_selected_to_active=True;scene.render.bake.cage_extrusion=.028;scene.render.bake.max_ray_distance=.12;scene.render.bake.margin=12
 target=material('Foe_4K_PBR_Runtime_Atlas',(.08,.09,.09),.5,.5);low.data.materials.clear();low.data.materials.append(target)
 for p in low.data.polygons:p.material_index=0
 n=target.node_tree.nodes;tex=n.new('ShaderNodeTexImage');tex.name='BAKE_TARGET';n.active=tex
 saved={}
 for ob in highs:
  for mat in ob.data.materials:
   if mat in saved:continue
   nodes=mat.node_tree.nodes;links=mat.node_tree.links;bs=nodes.get('Principled BSDF');output=next(q for q in nodes if q.type=='OUTPUT_MATERIAL');old=output.inputs['Surface'].links[0].from_socket
   emit=nodes.new('ShaderNodeEmission');saved[mat]=(old,bs,emit,output)
 images={}
 for mode in ['base-color','normal','orm']:
  img=bpy.data.images.new('foe-'+mode,width=4096,height=4096,alpha=False);img.colorspace_settings.name='sRGB' if mode=='base-color' else 'Non-Color';tex.image=img
  for mat,(old,bs,emit,output) in saved.items():
   links=mat.node_tree.links
   if mode=='normal':links.new(old,output.inputs['Surface']);continue
   links.new(emit.outputs[0],output.inputs['Surface'])
   for l in list(emit.inputs[0].links):links.remove(l)
   if mode=='base-color':
    inp=bs.inputs['Base Color']
    if inp.is_linked:links.new(inp.links[0].from_socket,emit.inputs[0])
    else:emit.inputs[0].default_value=inp.default_value
   else:
    combine=mat.node_tree.nodes.get('FoeBakeORM') or mat.node_tree.nodes.new('ShaderNodeCombineColor');combine.name='FoeBakeORM';combine.mode='RGB';combine.inputs[0].default_value=1
    for channel,param in [(1,'Roughness'),(2,'Metallic')]:
     inp=bs.inputs[param]
     if inp.is_linked:links.new(inp.links[0].from_socket,combine.inputs[channel])
     else:combine.inputs[channel].default_value=inp.default_value
    links.new(combine.outputs[0],emit.inputs[0])
  bpy.ops.object.select_all(action='DESELECT')
  for ob in highs:ob.hide_render=False;ob.select_set(True)
  low.select_set(True);bpy.context.view_layer.objects.active=low
  log('bake '+mode);bpy.ops.object.bake(type='NORMAL' if mode=='normal' else 'EMIT');img.filepath_raw=str(TEX/('foe-'+mode+'.png'));img.file_format='PNG';img.save();images[mode]=img
 # Bake actual high-surface occlusion into ORM red, keeping one shared packed map.
 import numpy as np
 ao=bpy.data.images.new('Foe_Baked_High_AO',width=4096,height=4096,alpha=False);ao.colorspace_settings.name='Non-Color';tex.image=ao;log('bake occlusion');bpy.ops.object.bake(type='AO')
 pixels=np.empty(len(images['orm'].pixels),dtype=np.float32);images['orm'].pixels.foreach_get(pixels);ap=np.empty(len(ao.pixels),dtype=np.float32);ao.pixels.foreach_get(ap);pixels[0::4]=ap[0::4];images['orm'].pixels.foreach_set(pixels);images['orm'].save();REPORT['occlusion']='4096x4096 selected-high AO baked and packed into ORM red'
 for mat,(old,bs,emit,output) in saved.items():mat.node_tree.links.new(old,output.inputs['Surface'])
 bs=n.get('Principled BSDF');links=target.node_tree.links
 tex.image=images['base-color'];links.new(tex.outputs['Color'],bs.inputs['Base Color'])
 norm=n.new('ShaderNodeTexImage');norm.image=images['normal'];nm=n.new('ShaderNodeNormalMap');links.new(norm.outputs['Color'],nm.inputs['Color']);links.new(nm.outputs['Normal'],bs.inputs['Normal'])
 orm=n.new('ShaderNodeTexImage');orm.image=images['orm'];separate=n.new('ShaderNodeSeparateColor');separate.mode='RGB';links.new(orm.outputs['Color'],separate.inputs[0]);links.new(separate.outputs[1],bs.inputs['Roughness']);links.new(separate.outputs[2],bs.inputs['Metallic'])
 settings=bpy.data.node_groups.new('glTF Material Output','ShaderNodeTree');settings.interface.new_socket(name='Occlusion',in_out='INPUT',socket_type='NodeSocketFloat');gn=n.new('ShaderNodeGroup');gn.node_tree=settings;links.new(separate.outputs[0],gn.inputs['Occlusion'])
 REPORT['textures']={k:{'path':str(TEX/('foe-'+k+'.png')),'width':4096,'height':4096,'sha256':sha(TEX/('foe-'+k+'.png'))} for k in images}
def studio(low):
 s=bpy.context.scene;s.render.engine='CYCLES';s.cycles.samples=20;s.render.resolution_x=900;s.render.resolution_y=1000;s.render.resolution_percentage=100;s.world=bpy.data.worlds.new('FoeSameLightStudio');s.world.use_nodes=True;s.world.node_tree.nodes['Background'].inputs[0].default_value=(.17,.17,.17,1)
 center=Vector((0,-.02,.86))
 for loc,power,size in [((2,-3,4),600,4),((-3,-1,2),400,3),((0,3,3),700,3)]:
  bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.data.energy=power;l.data.shape='DISK';l.data.size=size;l.rotation_euler=(center-l.location).to_track_quat('-Z','Y').to_euler()
 bpy.ops.object.camera_add(location=(0,-4,1));c=bpy.context.object;c.data.type='ORTHO';s.camera=c
 def shot(name,target,loc,scale,w=900,h=1000):
  c.location=loc;c.rotation_euler=(Vector(target)-c.location).to_track_quat('-Z','Y').to_euler();c.data.ortho_scale=scale;s.render.resolution_x=w;s.render.resolution_y=h;s.render.filepath=str(OUT/(name+'.png'));bpy.ops.render.render(write_still=True)
 for label,ob in [('source',SOURCE),('candidate',low)]:
  SOURCE.hide_render=label!='source';low.hide_render=label!='candidate'
  shot(label+'-full',(0,-.02,.86),(0,-4,1.06),2.064)
  shot(label+'-armor',(0,-.22,1.48),(0,-3,1.5),.53,1000,850)
  shot(label+'-hands',(.535,-.20,.79),(.8,-2,.95),.35,1000,700)
 SOURCE.hide_render=True;low.hide_render=False
 for side in ['f','b']:
  x=.535 if side=='f' else -.535
  for g in [0,.25,.5,.75,1]:
   for key in low.data.shape_keys.key_blocks:key.value=0
   low.data.shape_keys.key_blocks['grip_half_'+side].value=2*g if g<=.5 else 2*(1-g);low.data.shape_keys.key_blocks['grip_'+side].value=0 if g<=.5 else 2*g-1
   shot(f'hand-{side}-{g:.2f}',(x,-.18,.81),(x+.20,-1.6,.95),.31,900,700)
 for key in low.data.shape_keys.key_blocks:key.value=0
 original=low.data.materials[0];wire=material('EditableTopologyWirePreview',(.24,.31,.34),0,.7);low.data.materials[0]=wire
 wireob=low.copy();wireob.data=low.data.copy();bpy.context.collection.objects.link(wireob);wireob.name='True_Quad_Edge_Overlay';wireob.data.materials.clear();wireob.data.materials.append(material('TrueQuadEdgeInk',(.003,.004,.005),0,.9));wf=wireob.modifiers.new('Actual_editable_edges','WIREFRAME');wf.thickness=.00032;wf.offset=1;wf.use_replace=True
 shot('candidate-wireframe',(0,-.02,.86),(0,-4,1.06),2.064)
 shot('candidate-hand-wireframe',(.535,-.20,.79),(.8,-2,.95),.35,1000,700)
 bpy.data.objects.remove(wireob,do_unlink=True)
 low.data.materials[0]=original
def main():
 global SOURCE,ARM,LEATHER,METAL
 bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(ROOT/'baseline/assets/3d/foe-rigged.glb'))
 SOURCE=next(o for o in bpy.context.scene.objects if o.type=='MESH' and 'foe_HI' in o.name);SOURCE.name='Foe_Immutable_Source_Reference';ARM=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
 for o in list(bpy.context.scene.objects):
  if o not in [SOURCE,ARM]:bpy.data.objects.remove(o,do_unlink=True)
 REPORT['baseline']={'sha256':sha(ROOT/'baseline/assets/3d/foe-rigged.glb'),'geometry':stats(SOURCE),'missing_acceptance':['all four progressive hand morphs','full-body editable quad topology','independent segmented glove finger loops','new UV atlas']}
 welded=SOURCE.copy();welded.data=SOURCE.data.copy();bm=bmesh.new();bm.from_mesh(welded.data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.000004);bm.to_mesh(welded.data);bm.free();REPORT['baseline']['coordinate_welded_geometry']=stats(welded);bpy.data.meshes.remove(welded.data)
 LEATHER=material('Refined charcoal glove leather',(.067,.073,.076),.08,.68);METAL=material('Refined oxidized glove armor',(.145,.121,.108),.75,.39)
 n=LEATHER.node_tree.nodes;links=LEATHER.node_tree.links;noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=180;noise.inputs['Detail'].default_value=2;bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.08;bump.inputs['Distance'].default_value=.00035;links.new(noise.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs[0],n['Principled BSDF'].inputs['Normal'])
 n=METAL.node_tree.nodes;links=METAL.node_tree.links;noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=160;noise.inputs['Detail'].default_value=3;ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(.085,.078,.068,1);ramp.color_ramp.elements[1].color=(.18,.15,.12,1);links.new(noise.outputs['Fac'],ramp.inputs[0]);links.new(ramp.outputs[0],n['Principled BSDF'].inputs['Base Color']);rough=n.new('ShaderNodeMath');rough.operation='MULTIPLY_ADD';rough.inputs[1].default_value=.35;rough.inputs[2].default_value=.26;links.new(noise.outputs['Fac'],rough.inputs[0]);links.new(rough.outputs[0],n['Principled BSDF'].inputs['Roughness'])
 # Load the independently regenerated QuadriFlow result, not source indices.
 quadpath=OUT/'surface-pair-probe.blend';REPORT['base_method']='source_surface_coarsening_and_quad_pairing'
 with bpy.data.libraries.load(str(quadpath),link=False) as (a,b):b.meshes=list(a.meshes)
 mesh=max((m for m in b.meshes if m),key=lambda m:len(m.vertices));low=bpy.data.objects.new('Foe_Game_Retopology',mesh);bpy.context.collection.objects.link(low);low.matrix_world=SOURCE.matrix_world.copy()
 assert all(math.isfinite(c) for v in low.data.vertices for c in v.co),'Invalid QuadriFlow coordinates'
 REPORT['base_file']={'path':str(quadpath),'sha256':sha(quadpath)};REPORT['base_geometry']=stats(low);log('base '+str(REPORT['base_geometry']));cleanup_body(low);log('clean '+str(stats(low)));cut_hands(low);log('cut '+str(stats(low)));clean_cut_fragments(low);log('fragment '+str(stats(low)));refine_mask_and_edges(low);log('detail '+str(stats(low)));keys,ranges=build_gloves(low);low.data.validate(verbose=True);transfer_skin(low,SOURCE,ranges);highs=make_high(low);crystal_facets(low,highs[0]);atlas(low)
 # Preserve actual high and low before potentially expensive texture bake.
 SOURCE.hide_render=True
 for h in highs:h.hide_render=True;h.hide_set(True)
 active(low);bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'foe-prebake.blend'))
 for h in highs:h.hide_set(False)
 bake(low,highs)
 for h in highs:h.hide_render=True;h.hide_set(True)
 low.shape_key_add(name='Basis')
 for name,positions in keys.items():
  k=low.shape_key_add(name=name)
  for i,p in enumerate(positions):k.data[i].co=p
  k.value=0;k.slider_min=0;k.slider_max=1
 # Named editable masks expose exact hand membership and hard-surface decisions.
 for side,(a,b) in ranges.items():g=low.vertex_groups.new(name='AUTHOR_hand_mask_'+side);g.add(list(range(a,b)),1,'REPLACE')
 REPORT['geometry']=stats(low);REPORT['geometry']['quad_fraction']=REPORT['geometry']['quads']/REPORT['geometry']['polygons']
 REPORT['morphs']={}
 for k in low.data.shape_keys.key_blocks:
  if k.name=='Basis':continue
  moved=[i for i,(a,b) in enumerate(zip(k.data,low.data.shape_keys.key_blocks[0].data)) if (a.co-b.co).length>1e-7];side=k.name[-1];lo,hi=ranges[side];REPORT['morphs'][k.name]={'moved_vertices':len(moved),'max_delta':max(((k.data[i].co-low.data.vertices[i].co).length for i in moved),default=0),'outside_hand_moved':sum(not lo<=i<hi for i in moved)}
 sockets={'version':1,'role':'foe','space':'blender_world_z_up'}
 for side,name in [('f','front'),('b','rear')]:
  sign=1 if side=='f' else -1;a,b=ranges[side];sockets[name]={}
  for state,target,key in [('open',(sign*.535,-.163,.833),'Basis'),('half',(sign*.535,-.213,.778),'grip_half_'+side),('closed',(sign*.535,-.213,.777),'grip_'+side)]:
   shape=low.data.shape_keys.key_blocks[key];point=min((shape.data[i].co.copy() for i in range(a,b)),key=lambda p:(p-Vector(target)).length_squared);sockets[name][state]=list(low.matrix_world@point)
 (OUT/'contact-sockets.json').write_text(json.dumps(sockets,indent=2),encoding='utf8')
 studio(low)
 # Immutable/source/refined references are retained but hidden, selected export is exact.
 SOURCE.hide_render=True;SOURCE.hide_set(True)
 active(low);ARM.select_set(True)
 low['retopology_provenance']='Source-surface-aware 90% coarsening, full-body quad re-pairing, new mask gasket networks, wrist/thumb web reconstruction and physical glove cross-sections';low['source_sha256']=REPORT['baseline']['sha256']
 bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'foe-retopology.blend'))
 bpy.ops.export_scene.gltf(filepath=str(OUT/'foe-raw.glb'),export_format='GLB',use_selection=True,export_skins=True,export_morph=True,export_morph_normal=True,export_tangents=True,export_animations=False,export_apply=False,export_yup=True,export_extras=True)
 REPORT['elapsed_seconds']=time.time()-START;REPORT['output_sha256']={n:sha(OUT/n) for n in ['foe-retopology.blend','foe-raw.glb','contact-sockets.json']};REPORT['limits']=['Full-body source-aware coarsening and quad pairing preserves thin armor/cloth better than the rejected QuadriFlow seeds. New hand root/web/finger/thumb and mask loops are procedural authored geometry. Dorsal plates, rivets and mask gaskets are enclosed shells; thumbs/fingers connect to the body.','Game clip/framerate/sole/contact verification is owned by root after canonical export.'];(OUT/'build-report.json').write_text(json.dumps(REPORT,indent=2),encoding='utf8');log(json.dumps(REPORT['geometry']))
if __name__=='__main__':main()
