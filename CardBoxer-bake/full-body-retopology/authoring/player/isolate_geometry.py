import bpy,bmesh,json,os
from mathutils import Vector
O=os.path.dirname(os.path.abspath(__file__));bpy.ops.wm.open_mainfile(filepath=O+'/topology-diagnostic.blend');low=bpy.data.objects['PLAYER_Retopo_Game_Quads'];source=bpy.data.objects['SOURCE_player_immutable'];s=bpy.context.scene
for ob in s.objects:
 if ob.type=='MESH':ob.hide_render=ob!=low
low.hide_set(False)
bm=bmesh.new();bm.from_mesh(low.data);print('TOPOLOGY',len(bm.verts),len(bm.faces),'boundary',sum(e.is_boundary for e in bm.edges),'nonmanifold',sum(not e.is_manifold for e in bm.edges),'zeroarea',sum(f.calc_area()<1e-12 for f in bm.faces));bm.free()
print('VALIDATE',low.data.validate(verbose=True,clean_customdata=False))
clay=bpy.data.materials.new('Diagnostic clay');clay.use_nodes=True;clay.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.6,.6,.6,1);clay.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.55
s.world=bpy.data.worlds.new('studio');s.world.use_nodes=True;s.world.node_tree.nodes['Background'].inputs[0].default_value=(.17,.17,.17,1);s.render.engine='CYCLES';s.cycles.samples=24;s.render.resolution_x=1000;s.render.resolution_y=700;s.render.resolution_percentage=100
for loc,power,size in [((2,-3,4),600,4),((-3,-1,2),400,3),((0,3,3),700,3)]:
 bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.data.energy=power;l.data.size=size;l.rotation_euler=(Vector((0,0,.86))-l.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add();s.camera=bpy.context.object;s.camera.data.type='ORTHO';s.camera.data.ortho_scale=.42;s.camera.location=(0,-3,1.55);s.camera.rotation_euler=(Vector((0,-.16,1.55))-s.camera.location).to_track_quat('-Z','Y').to_euler()
for p in low.data.polygons:p.material_index=0
low.data.materials.clear();low.data.materials.append(clay);s.render.filepath=O+'/fresh-low-clay.png';bpy.ops.render.render(write_still=True)
for ob in s.objects:
 if ob.type=='MESH':ob.hide_render=ob!=source
source.hide_set(False);source.data.materials.clear();source.data.materials.append(clay);s.render.filepath=O+'/fresh-source-clay.png';bpy.ops.render.render(write_still=True)
