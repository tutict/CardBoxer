"""Continue the saved v7 mesh: local cuff correction, bounded bake and export copy."""
import bpy,bmesh,math,json,sys,importlib.util,time,hashlib
from pathlib import Path
from mathutils import Vector
OUT=Path(__file__).resolve().parent;ROOT=OUT.parent.parent
spec=importlib.util.spec_from_file_location('foe_author',ROOT/'tools/author_foe.py');author=importlib.util.module_from_spec(spec);spec.loader.exec_module(author)
bpy.ops.wm.open_mainfile(filepath=str(OUT/'foe-retopology.blend'))
low=bpy.data.objects['Foe_Game_Retopology'];source=bpy.data.objects['Foe_Immutable_Source_Reference'];arm=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
report=json.loads((OUT/'build-report.json').read_text());author.REPORT=report;author.SOURCE=source;author.ARM=arm
keys=low.data.shape_keys.key_blocks;original_count=report['body_vertices_before_hands']
# The old zipper preserved non-monotonic source cut loops. Regularize only those
# existing boundary vertices; all body loops, authored fingers and quad mesh remain.
for side,(begin,end) in report['hand_vertex_ranges'].items():
 sign=1 if side=='f' else -1
 bridge=[p for p in low.data.polygons if any(i<original_count for i in p.vertices) and any(begin<=i<end for i in p.vertices)]
 ids=set(i for p in bridge for i in p.vertices if i<original_count)
 adjacency={i:[] for i in ids}
 edge_faces={}
 for p in low.data.polygons:
  for ek in p.edge_keys:edge_faces.setdefault(tuple(sorted(ek)),[]).append(p.index)
 bridge_ids={p.index for p in bridge}
 for e in low.data.edges:
  a,b=e.vertices
  linked=edge_faces[tuple(sorted((a,b)))]
  if a in ids and b in ids and any(p in bridge_ids for p in linked) and any(p not in bridge_ids for p in linked):adjacency[a].append(b);adjacency[b].append(a)
 start=min(ids);seq=[start];prev=None;cur=start
 while True:
  opts=[i for i in adjacency[cur] if i!=prev and (i not in seq or i==start)]
  if not opts:break
  nxt=opts[0]
  if nxt==start:break
  seq.append(nxt);prev,cur=cur,nxt
 if len(seq)!=len(ids):
  print('CUFF DIAG',side,'bridge',len(bridge),'degree', {d:sum(len(v)==d for v in adjacency.values()) for d in range(6)},'seq',len(seq),'ids',len(ids),'miss',[(i,list(low.data.vertices[i].co),adjacency[i]) for i in ids if i not in seq],flush=True)
 # A self-touching 99-step cut has 98 unique vertices: the old code treated
 # its secondary concave lobe as part of the wrist, producing crossed strips.
 # Keep the outer cycle and close the short crevice independently below.
 report.setdefault('cuff_cut_diagnosis',{})[side]={'all_unique':len(ids),'outer_cycle':len(seq),'branch_vertices':sum(len(v)>2 for v in adjacency.values())}
 center=sum((low.data.vertices[i].co for i in seq),Vector())/len(seq)
 signed=sum(low.data.vertices[seq[j]].co.x*low.data.vertices[seq[(j+1)%len(seq)]].co.y-low.data.vertices[seq[(j+1)%len(seq)]].co.x*low.data.vertices[seq[j]].co.y for j in range(len(seq)))
 direction=1 if signed>0 else -1
 # Locate source ring start around the closest matching angle, then fit the bridge.
 angle=math.atan2(low.data.vertices[start].co.y-center.y,low.data.vertices[start].co.x-center.x)
 for j,i in enumerate(seq):
  a=angle+direction*j*math.tau/len(seq);p=Vector((center.x+.070*math.cos(a),center.y+.064*math.sin(a),.916))
  low.data.vertices[i].co=p
  for key in keys:key.data[i].co=p
 report.setdefault('resume_cuff',{})[side]={'regularized_boundary_vertices':len(seq),'center':list(center),'cuff_z':.916}
low.data.update()
# Cuff bridge correspondence must be refit after regularization without changing
# any vertex index (shape masks/UV/weights remain valid).
bm=bmesh.new();bm.from_mesh(low.data);bm.verts.ensure_lookup_table();bm.verts.index_update()
delete=[];new=[]
for side,(begin,end) in report['hand_vertex_ranges'].items():
 bridge=[f for f in bm.faces if any(v.index<original_count for v in f.verts) and any(begin<=v.index<end for v in f.verts)]
 body=set(v for f in bridge for v in f.verts if v.index<original_count);palm=set(v for f in bridge for v in f.verts if begin<=v.index<end)
 def cycle(group):
  start=min(group,key=lambda v:v.index);seq=[start];prev=None;cur=start
  while True:
   opts=[e.other_vert(cur) for e in cur.link_edges if e.other_vert(cur) in group and any(f in bridge for f in e.link_faces) and any(f not in bridge for f in e.link_faces) and e.other_vert(cur)!=prev and (e.other_vert(cur) not in seq or e.other_vert(cur)==start)]
   if not opts or opts[0]==start:break
   nxt=opts[0];seq.append(nxt);prev,cur=cur,nxt
  return seq
 a=cycle(body);b=cycle(palm);candidates=[]
 for order in [a,list(reversed(a))]:
  for shift in range(len(a)):
   seq=order[shift:]+order[:shift];score=sum((seq[int(j*len(seq)/len(b))].co-v.co).length_squared for j,v in enumerate(b));candidates.append((score,seq))
 bridge_indices=[];author.zipper([v.index for v in min(candidates,key=lambda q:q[0])[1]],[v.index for v in b],bridge_indices)
 new.extend(bridge_indices);delete.extend(bridge)
bmesh.ops.delete(bm,geom=delete,context='FACES_ONLY')
for f in new:
 face=bm.faces.new([bm.verts[i] for i in f]);face.smooth=True;face.material_index=0
remaining=[e for e in bm.edges if e.is_boundary]
if remaining:
 filled=bmesh.ops.holes_fill(bm,edges=remaining,sides=0)
 for f in filled.get('faces',[]):f.material_index=0;f.smooth=True
bmesh.ops.delete(bm,geom=[e for e in bm.edges if not e.link_faces],context='EDGES')
bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(low.data);bm.free();low.data.update()
# Rebuild the refined hand source from the updated low region, leaving immutable
# source and the source-aware body mesh in place. Temporary save enables inspection.
for name in ['Foe_Refined_High_Surface','Foe_High_Glove_Panels','Foe_High_Controlled_Mask_Edges']:
 o=bpy.data.objects.get(name)
 if o:bpy.data.objects.remove(o,do_unlink=True)
author.LEATHER=bpy.data.materials.get('Refined charcoal glove leather');author.METAL=bpy.data.materials.get('Refined oxidized glove armor')
# Existing low atlas material must not be used for the high glove rebake. Restore
# source/leather/metal assignments from spatial authored regions.
low.data.materials.clear()
for mat in [source.data.materials[0],author.LEATHER,author.METAL]:low.data.materials.append(mat)
for p in low.data.polygons:
 ids=list(p.vertices)
 if all(i<original_count for i in ids):p.material_index=2 if all(report['surface_detail_vertex_range'][0]<=i<report['surface_detail_vertex_range'][1] for i in ids) else 0
 else:
  center=p.center;p.material_index=1
  if center.y<-.220 and .80<center.z<.88:p.material_index=2
  elif any(a<=i<b for a,b in [(33700,33852),(34482,34634)] for i in ids):p.material_index=2
highs=author.make_high(low)
author.crystal_facets(low,highs[0]);author.atlas(low)
for h in highs:h.hide_render=True;h.hide_set(True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'resume-working.blend'))
if '--probe' in sys.argv:
 for o in bpy.context.scene.objects:
  if o.type=='MESH':o.hide_render=o!=low
 s=bpy.context.scene;s.cycles.samples=12;c=s.camera
 c.location=(.8,-2,.95);c.rotation_euler=(Vector((.535,-.20,.87))-c.location).to_track_quat('-Z','Y').to_euler();c.data.ortho_scale=.34;s.render.resolution_x=900;s.render.resolution_y=700;s.render.filepath=str(OUT/'probe-cuff.png');bpy.ops.render.render(write_still=True)
 print('PROBE',author.stats(low));sys.exit()
for h in highs:h.hide_set(False)
author.bake(low,highs)
for h in highs:h.hide_render=True;h.hide_set(True)
source.hide_render=True;source.hide_set(True)
author.studio(low)
for key in keys:key.value=0
report['geometry']=author.stats(low);report['geometry']['quad_fraction']=report['geometry']['quads']/report['geometry']['polygons']
author.active(low);arm.select_set(True);bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'foe-retopology.blend'))
author.export_low(low,arm)
report['output_sha256']={n:author.sha(OUT/n) for n in ['foe-retopology.blend','foe-raw.glb','contact-sockets.json']}
(OUT/'build-report.json').write_text(json.dumps(report,indent=2))
print('RESUME COMPLETE',report['geometry'],flush=True)
