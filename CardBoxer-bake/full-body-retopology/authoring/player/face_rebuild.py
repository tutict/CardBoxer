"""Closed structured facial quad surface with integrated eye and lip rings."""
import bmesh,math
from mathutils import Vector

def width(z):
 points=[(1.419,.050),(1.450,.077),(1.485,.091),(1.530,.105),(1.593,.107)]
 for (a,x),(b,y) in zip(points,points[1:]):
  if a<=z<=b:return x+(y-x)*(z-a)/(b-a)
 return points[0][1] if z<points[0][0] else points[-1][1]

def reconstruct(low,bvh):
 def sample(x,z):
  p,n,fi,d=bvh.ray_cast(Vector((x,-.8,z)),Vector((0,1,0)),.70)
  if p is None:p,n,fi,d=bvh.find_nearest(Vector((x,-.30,z)))
  p=p.copy()
  # Keep the sampled silhouette and feature positions. Median depth removes
  # sub-millimeter scan ridges before they become crease-shaped low quads.
  depths=[p.y]
  for dx,dz in [(-.001,0),(.001,0),(0,-.001),(0,.001)]:
   q,_,_,_=bvh.ray_cast(Vector((x+dx,-.8,z+dz)),Vector((0,1,0)),.70)
   if q is not None and abs(q.y-p.y)<.006:depths.append(q.y)
  p.y=sorted(depths)[len(depths)//2]-.00015;return p
 plate=bmesh.new();rows=[];nx=32;nz=30
 for j in range(nz+1):
  z=1.419+(1.593-1.419)*j/nz;row=[]
  for i in range(nx+1):row.append(plate.verts.new(sample(width(z)*(2*i/nx-1),z)))
  rows.append(row)
 for j in range(nz):
  for i in range(nx):plate.faces.new((rows[j][i],rows[j][i+1],rows[j+1][i+1],rows[j+1][i]))
 features={}
 for label,cx,cz,rx,rz in [('eye_b',-.043,1.53,.037,.024),('eye_f',.043,1.53,.037,.024),('lips',0,1.460,.026,.010)]:
  def r(p):return math.sqrt(((p.x-cx)/rx)**2+((p.z-cz)/rz)**2)
  cut=[f for f in plate.faces if r(f.calc_center_median())<1.04]
  bmesh.ops.delete(plate,geom=cut,context='FACES')
  edges=[e for e in plate.edges if e.is_boundary]
  adj={}
  for e in edges:
   for v in e.verts:adj.setdefault(v,[]).append(e.other_vert(v))
  assert adj and all(len(v)==2 for v in adj.values()),label+' non-loop boundary'
  unseen=set(adj);components=[]
  while unseen:
   seed=unseen.pop();component={seed};stack=[seed]
   while stack:
    for v in adj[stack.pop()]:
     if v in unseen:unseen.remove(v);component.add(v);stack.append(v)
   components.append(component)
  component=min(components,key=lambda vs:r(sum((v.co for v in vs),Vector())/len(vs)))
  adj={v:ns for v,ns in adj.items() if v in component}
  start=next(iter(adj));chain=[start];prev=None;cur=start
  while True:
   nxt=next(v for v in adj[cur] if v!=prev)
   if nxt==start:break
   chain.append(nxt);prev,cur=cur,nxt
  assert len(chain)==len(adj),label+' extra hole'
  ring=chain
  for scale in [.97,.82,.64,.40,.20]:
   new=[]
   for v in chain:
    t=math.atan2((v.co.z-cz)/rz,(v.co.x-cx)/rx);new.append(plate.verts.new(sample(cx+rx*scale*math.cos(t),cz+rz*scale*math.sin(t))))
   for k in range(len(chain)):
    q=(k+1)%len(chain);plate.faces.new((ring[k],ring[q],new[q],new[k]))
   ring=new
  center=plate.verts.new(sample(cx,cz))
  for k in range(len(chain)):plate.faces.new((ring[k],ring[(k+1)%len(chain)],center))
  features[label]={'connected_to_face_grid':True,'boundary_vertices':len(chain),'concentric_rings':5}
 bmesh.ops.delete(plate,geom=[v for v in plate.verts if not v.link_faces],context='VERTS')
 frontverts=list(plate.verts);frontfaces=list(plate.faces);outer=[e for e in plate.edges if e.is_boundary]
 back={v:plate.verts.new(v.co+Vector((0,.004,0))) for v in frontverts}
 for f in frontfaces:plate.faces.new(tuple(back[v] for v in reversed(f.verts)))
 for e in outer:plate.faces.new((e.verts[0],back[e.verts[0]],back[e.verts[1]],e.verts[1]))
 assert all(e.is_manifold for e in plate.edges),'Facial surface is not closed'
 bmesh.ops.recalc_face_normals(plate,faces=list(plate.faces))

 # Close the replaced scan front into the head interior, then attach the closed
 # facial plate as an intentional component under the hair/jaw boundary.
 bm=bmesh.new();bm.from_mesh(low.data)
 cut=[f for f in bm.faces if (1.420<f.calc_center_median().z<1.592 and abs(f.calc_center_median().x)<width(f.calc_center_median().z)-.003 and f.calc_center_median().y<-.252)]
 bmesh.ops.delete(bm,geom=cut,context='FACES')
 edges=[e for e in bm.edges if e.is_boundary]
 # BMesh fills each boundary once. The previous vertex walk could enter
 # another connected branch, cap it again, and give forehead edges 3-4 faces.
 caps=bmesh.ops.holes_fill(bm,edges=edges,sides=0)['faces'] if edges else []
 poked=bmesh.ops.poke(bm,faces=caps,offset=0,use_relative_offset=False) if caps else {'verts':[],'faces':[]}
 for center in poked['verts']:
  center.co.y+=.075 if center.co.z>1.40 and abs(center.co.x)<.15 else .0005
 capcount=len(poked['faces'])
 bmesh.ops.delete(bm,geom=[v for v in bm.verts if not v.link_faces],context='VERTS')
 vm={v:bm.verts.new(v.co) for v in plate.verts}
 for f in plate.faces:bm.faces.new(tuple(vm[v] for v in f.verts))
 plate.free();bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(low.data);bm.free()
 return {'features':features,'grid':[nx,nz],'internal_cap_triangles':capcount,'closed_face_component':True}
