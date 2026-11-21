import bpy,os,json
from mathutils import Vector
O=os.path.dirname(os.path.abspath(__file__));bpy.ops.wm.open_mainfile(filepath=O+'/source-inspect.blend');s=bpy.context.scene
for o in s.objects:
 if o.type=='MESH' and not o.name.startswith('foe_HI'):o.hide_render=True
s.render.resolution_x=1000;s.render.resolution_y=700
for name,target,loc,scale in [('face',(0,-.22,1.53),(0,-3,1.53),.46),('hands',(.52,-.20,.80),(.8,-2,.95),.35),('hand-back',(.52,-.20,.80),(.6,2,.95),.35)]:
 c=s.camera;c.location=loc;c.rotation_euler=(Vector(target)-c.location).to_track_quat('-Z','Y').to_euler();c.data.ortho_scale=scale;s.render.filepath=O+'/source-'+name+'.png';bpy.ops.render.render(write_still=True)

