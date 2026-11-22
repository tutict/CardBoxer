import bpy,bmesh,os,json
O=os.path.dirname(os.path.abspath(__file__));bpy.ops.wm.open_mainfile(filepath=O+'/player-retopology.blend');ob=bpy.data.objects['PLAYER_Retopo_Game_Quads'];bm=bmesh.new();bm.from_mesh(ob.data);d=[[(list(v.co)) for v in e.verts] for e in bm.edges if e.is_boundary];print(json.dumps(d))
