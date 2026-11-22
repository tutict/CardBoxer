import bpy,os,json
from mathutils import Vector
O=os.path.dirname(os.path.abspath(__file__));bpy.ops.wm.open_mainfile(filepath=O+'/source-inspect.blend');s=bpy.context.scene
for o in s.objects:
 if o.type=='MESH' and not o.name.startswith('player_HI'):o.hide_render=True
s.render.resolution_x=1000;s.render.resolution_y=700
for name,target,loc,scale in [('face',(0,-.16,1.55),(0,-3,1.55),.42),('hands',(.535,-.225,.96),(.8,-2,1.25),.27),('hand-back',(.535,-.225,.96),(.6,2,1.2),.27)]:
 c=s.camera;c.location=loc;c.rotation_euler=(Vector(target)-c.location).to_track_quat('-Z','Y').to_euler();c.data.ortho_scale=scale;s.render.filepath=O+'/source-'+name+'.png';bpy.ops.render.render(write_still=True)
