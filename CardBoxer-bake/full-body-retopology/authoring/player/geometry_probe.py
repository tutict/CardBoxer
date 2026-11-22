import bpy,bmesh,json,os
O=os.path.dirname(os.path.abspath(__file__));bpy.ops.wm.open_mainfile(filepath=O+'/player-retopology.blend');ob=bpy.data.objects['PLAYER_Retopo_Game_Quads'];bm=bmesh.new();bm.from_mesh(ob.data)
bad=[{'a':list(e.verts[0].co),'b':list(e.verts[1].co),'faces':len(e.link_faces),'ids':[v.index for v in e.verts]} for e in bm.edges if not e.is_manifold]
json.dump(bad,open(O+'/nonmanifold-before.json','w'),indent=2);print(json.dumps(bad))
src=bmesh.new();src.from_mesh(bpy.data.objects['SOURCE_player_immutable'].data);bmesh.ops.remove_doubles(src,verts=list(src.verts),dist=.000004)
print('SOURCE_WELDED',sum(e.is_boundary for e in src.edges),sum(not e.is_manifold for e in src.edges))
