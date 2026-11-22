import bpy, json, os, sys
from mathutils import Vector
ROOT=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT=os.path.dirname(os.path.abspath(__file__))
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.join(ROOT,'baseline/assets/3d/player-rigged.glb'))
report=[]
for ob in bpy.context.scene.objects:
 d={'name':ob.name,'type':ob.type,'matrix':[list(row) for row in ob.matrix_world]}
 if ob.type=='MESH':
  d.update(vertices=len(ob.data.vertices),faces=len(ob.data.polygons),triangles=sum(len(p.vertices)-2 for p in ob.data.polygons),bounds=[list(v) for v in ob.bound_box],groups=[g.name for g in ob.vertex_groups],materials=[m.name for m in ob.data.materials],shape_keys=[k.name for k in ob.data.shape_keys.key_blocks] if ob.data.shape_keys else [])
  d['group_bounds']={}
  for g in ob.vertex_groups:
   vs=[v.co for v in ob.data.vertices if any(i.group==g.index and i.weight>.4 for i in v.groups)]
   if vs:d['group_bounds'][g.name]={'count':len(vs),'min':[min(v[i] for v in vs) for i in range(3)],'max':[max(v[i] for v in vs) for i in range(3)]}
 if ob.type=='ARMATURE': d['bones']=[{'name':b.name,'head':list(b.head_local),'tail':list(b.tail_local),'parent':b.parent.name if b.parent else None} for b in ob.data.bones]
 report.append(d)
json.dump(report,open(os.path.join(OUT,'source-inspect.json'),'w'),indent=2)
for img in bpy.data.images: print('IMAGE',img.name,img.size[:],img.filepath)
scene=bpy.context.scene
scene.render.engine='CYCLES';scene.cycles.samples=24
scene.render.resolution_x=900;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
scene.world=bpy.data.worlds.new('Studio');scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.17,.17,.17,1)
mesh=next(o for o in scene.objects if o.type=='MESH'); coords=[mesh.matrix_world@v.co for v in mesh.data.vertices]
mn=Vector([min(v[i] for v in coords) for i in range(3)]);mx=Vector([max(v[i] for v in coords) for i in range(3)]);center=(mn+mx)/2
def camera(loc,target,scale):
 bpy.ops.object.camera_add(location=loc);cam=bpy.context.object;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=scale;scene.camera=cam
for loc,power,size in [((2,-3,4),600,4),((-3,-1,2),400,3),((0,3,3),700,3)]:
 bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.data.energy=power;l.data.shape='DISK';l.data.size=size;l.rotation_euler=(center-l.location).to_track_quat('-Z','Y').to_euler()
camera(center+Vector((0,-4,.2)),center,(mx.z-mn.z)*1.2)
scene.render.filepath=os.path.join(OUT,'source-full.png');bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT,'source-inspect.blend'))
