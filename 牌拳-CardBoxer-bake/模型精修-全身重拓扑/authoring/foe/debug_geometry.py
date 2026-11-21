import bpy,sys
from pathlib import Path
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'));import author_foe as f
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(R/'baseline/assets/3d/foe-rigged.glb'))
f.SOURCE=next(o for o in bpy.context.scene.objects if o.type=='MESH' and 'foe_HI' in o.name)
with bpy.data.libraries.load(str(R/'authoring/foe/quadflow-probe.blend')) as (a,b):b.meshes=list(a.meshes)
mesh=max(b.meshes,key=lambda m:len(m.vertices));low=bpy.data.objects.new('low',mesh);bpy.context.collection.objects.link(low)
print('BEFORE',[[*low.data.vertices[i].co] for i in [0,100,1000,20000]],flush=True)
from mathutils.bvhtree import BVHTree
from mathutils import Vector
tree=BVHTree.FromPolygons([v.co.copy() for v in f.SOURCE.data.vertices],[list(p.vertices) for p in f.SOURCE.data.polygons])
print('NEAREST',[tree.find_nearest(low.data.vertices[i].co) for i in [0,100,1000,20000]],flush=True)
f.cleanup_body(low)
print('AFTER',[[*low.data.vertices[i].co] for i in [0,100,1000,20000]],flush=True)
bpy.ops.wm.save_as_mainfile(filepath=str(R/'authoring/foe/debug-geometry.blend'))
