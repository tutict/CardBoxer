import bpy,bmesh,math,json,sys,time
from pathlib import Path
O=Path(__file__).resolve().parent;R=O.parents[1];sys.path.insert(0,str(R/'tools'));import author_foe as f
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(R/'baseline/assets/3d/foe-rigged.glb'))
ob=next(o for o in bpy.context.scene.objects if o.type=='MESH' and 'foe_HI' in o.name);f.active(ob)
for mod in list(ob.modifiers):ob.modifiers.remove(mod)
bm=bmesh.new();bm.from_mesh(ob.data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.000004);bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=1e-9);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(ob.data);bm.free();ob.data.update()
dec=ob.modifiers.new('Controlled_surface_coarsening_90percent','DECIMATE');dec.ratio=.90;bpy.ops.object.modifier_apply(modifier=dec.name)
bm=bmesh.new();bm.from_mesh(ob.data);bmesh.ops.join_triangles(bm,faces=list(bm.faces),angle_face_threshold=math.radians(55),angle_shape_threshold=math.radians(85),cmp_seam=False,cmp_sharp=False,cmp_uvs=False,cmp_vcols=False,cmp_materials=False);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(ob.data);bm.free();ob.data.update()
assert all(math.isfinite(c) for v in ob.data.vertices for c in v.co)
print('SURFACE_PAIR',json.dumps(f.stats(ob)),flush=True);bpy.ops.wm.save_as_mainfile(filepath=str(O/'surface-pair-probe.blend'))
