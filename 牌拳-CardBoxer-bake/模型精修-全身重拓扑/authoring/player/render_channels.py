import bpy,os
from mathutils import Vector
O=os.path.dirname(os.path.abspath(__file__));bpy.ops.wm.open_mainfile(filepath=O+'/player-retopology.blend');low=bpy.data.objects['PLAYER_Retopo_Game_Quads'];s=bpy.context.scene;cam=s.camera;s.render.resolution_x=1000;s.render.resolution_y=700;cam.location=(0,-3,1.55);cam.rotation_euler=(Vector((0,-.16,1.55))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=.42
mat=low.data.materials[0];nt=mat.node_tree;bs=nt.nodes['Principled BSDF'];old=list(bs.inputs['Normal'].links)
for link in old:nt.links.remove(link)
s.render.filepath=O+'/candidate-face-baseonly.png';bpy.ops.render.render(write_still=True)
bs.inputs['Base Color'].default_value=(.6,.6,.6,1)
for link in list(bs.inputs['Base Color'].links):nt.links.remove(link)
s.render.filepath=O+'/candidate-face-geometryonly.png';bpy.ops.render.render(write_still=True)
