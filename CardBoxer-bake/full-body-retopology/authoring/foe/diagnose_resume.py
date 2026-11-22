import bpy,bmesh,json,math,sys
from pathlib import Path
from mathutils import Vector
OUT=Path(__file__).resolve().parent
bpy.ops.wm.open_mainfile(filepath=str(OUT/'foe-retopology.blend'))
low=bpy.data.objects['Foe_Game_Retopology'];source=bpy.data.objects['Foe_Immutable_Source_Reference']
s=bpy.context.scene;s.cycles.samples=12;c=s.camera
for o in s.objects:
 if o.type=='MESH':o.hide_render=o!=low
def shot(name,target,loc,scale,w=900,h=700):
 c.location=loc;c.rotation_euler=(Vector(target)-c.location).to_track_quat('-Z','Y').to_euler();c.data.ortho_scale=scale;s.render.resolution_x=w;s.render.resolution_y=h;s.render.filepath=str(OUT/('diagnostic-'+name+'.png'));bpy.ops.render.render(write_still=True)
mat=low.data.materials[0];bs=mat.node_tree.nodes.get('Principled BSDF')
for link in list(bs.inputs['Normal'].links):mat.node_tree.links.remove(link)
shot('no-normal-cuff',(.535,-.20,.87),(.8,-2,.95),.34)
shot('no-normal-mask',(0,-.22,1.52),(0,-3,1.5),.49,1000,850)
clay=bpy.data.materials.new('Diagnostic Clay');clay.diffuse_color=(.25,.25,.25,1);clay.use_nodes=True;clay.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.25,.25,.25,1);clay.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.6
low.data.materials[0]=clay
shot('clay-cuff',(.535,-.20,.87),(.8,-2,.95),.34)
shot('clay-mask',(0,-.22,1.52),(0,-3,1.5),.49,1000,850)
bm=bmesh.new();bm.from_mesh(low.data)
long=[{'length':e.calc_length(),'v':[list(v.co) for v in e.verts]} for e in bm.edges if e.calc_length()>.10 and all(abs(v.co.x)>.395 and .87<v.co.z<.96 for v in e.verts)]
ngons=[{'index':f.index,'vertices':len(f.verts),'center':list(f.calc_center_median())} for f in bm.faces if len(f.verts)>4]
(OUT/'diagnostic-geometry.json').write_text(json.dumps({'long_cuff_edges':sorted(long,key=lambda a:-a['length']),'ngons':ngons},indent=2));bm.free()
print('DIAG',len(long),'long cuff edges;',len(ngons),'ngons',flush=True)
