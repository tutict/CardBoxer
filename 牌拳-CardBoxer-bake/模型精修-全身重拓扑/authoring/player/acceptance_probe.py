"""Read-only acceptance evidence from the saved candidate, including export PBR."""
import bpy,bmesh,json,os,struct,numpy as np
from mathutils import Vector
O=os.path.dirname(os.path.abspath(__file__))
bpy.ops.wm.open_mainfile(filepath=O+'/player-retopology.blend')
ob=bpy.data.objects['PLAYER_Retopo_Game_Quads']; me=ob.data
bm=bmesh.new();bm.from_mesh(me)
uv=me.uv_layers.active;me.calc_loop_triangles()
normal=bpy.data.images['player-normal-4k'];px=np.empty(len(normal.pixels),np.float32);normal.pixels.foreach_get(px);px=px.reshape(normal.size[1],normal.size[0],4)
facepixels=[]
for tr in me.loop_triangles:
 c=sum((me.vertices[i].co for i in tr.vertices),Vector())/3
 if c.y<-.24 and c.z>1.4:
  u=sum((uv.data[i].uv for i in tr.loops),Vector((0,0)))/3
  facepixels.append(px[min(4095,max(0,int(u.y*4096))),min(4095,max(0,int(u.x*4096))),:3].tolist())
fp=np.array(facepixels)
b=open(O+'/player-raw.glb','rb').read();length=struct.unpack_from('<I',b,12)[0];g=json.loads(b[20:20+length]);prim=g['meshes'][0]['primitives'][0];mat=g['materials'][prim['material']]
stats={'triangles':sum(len(p.vertices)-2 for p in me.polygons),'boundary_edges':sum(e.is_boundary for e in bm.edges),'nonmanifold_edges':sum(not e.is_manifold for e in bm.edges),'normal_face_samples':len(fp),'normal_face_negative_z_fraction':float((fp[:,2]<.50).mean()),'normal_face_dark_fraction':float((fp.max(1)<.2).mean()),'export_tangent': 'TANGENT' in prim['attributes'],'export_occlusion': 'occlusionTexture' in mat,'texture_uv_layers':[x.name for x in me.uv_layers]}
json.dump(stats,open(O+'/acceptance-before.json','w'),indent=2);print(json.dumps(stats,indent=2))
assert stats['export_tangent'] and stats['export_occlusion'], 'FAIL: canonical tangent and packed ORM AO missing'
