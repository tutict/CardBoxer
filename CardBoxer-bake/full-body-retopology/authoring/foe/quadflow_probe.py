import bpy,bmesh,json,os,time,math
O=os.path.dirname(os.path.abspath(__file__));R=os.path.dirname(os.path.dirname(O))
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=R+'/baseline/assets/3d/foe-rigged.glb')
ob=next(o for o in bpy.context.scene.objects if o.name.startswith('foe_HI'))
bpy.context.view_layer.objects.active=ob;bpy.ops.object.select_all(action='DESELECT');ob.select_set(True)
bm=bmesh.new();bm.from_mesh(ob.data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=0.000004);bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=1e-9);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(ob.data);bm.free()
print('WELDED',len(ob.data.vertices),len(ob.data.polygons),flush=True)
t=time.time();bpy.ops.object.quadriflow_remesh(target_faces=36000,use_preserve_sharp=True,use_preserve_boundary=True,use_mesh_symmetry=False,seed=31)
print('QUADFLOW',time.time()-t,len(ob.data.vertices),len(ob.data.polygons),flush=True)
assert all(math.isfinite(c) for v in ob.data.vertices for c in v.co),'QuadriFlow invalid coordinates'
bpy.ops.wm.save_as_mainfile(filepath=O+'/quadflow-probe.blend')


