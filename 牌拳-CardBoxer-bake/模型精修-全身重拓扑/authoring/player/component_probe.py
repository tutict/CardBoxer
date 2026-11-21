import bpy,bmesh,os,json
O=os.path.dirname(os.path.abspath(__file__));bpy.ops.wm.open_mainfile(filepath=O+'/source-inspect.blend');ob=bpy.data.objects['player_HI_skinned'];bm=bmesh.new();bm.from_mesh(ob.data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.000004)
un=set(bm.verts);comps=[]
while un:
 seed=un.pop();vs={seed};stack=[seed]
 while stack:
  v=stack.pop()
  for e in v.link_edges:
   n=e.other_vert(v)
   if n in un:un.remove(n);vs.add(n);stack.append(n)
 fs=set(f for v in vs for f in v.link_faces);comps.append({'vertices':len(vs),'faces':len(fs),'min':[min(v.co[i] for v in vs) for i in range(3)],'max':[max(v.co[i] for v in vs) for i in range(3)]})
print('COMPONENTS',json.dumps(sorted(comps,key=lambda c:-c['faces'])))
