import bpy,os,json,numpy as np
O=os.path.dirname(os.path.abspath(__file__));bpy.ops.wm.open_mainfile(filepath=O+'/source-inspect.blend');ob=bpy.data.objects['player_HI_skinned'];im=bpy.data.images['texture_pbr_20250901'];p=np.empty(len(im.pixels),np.float32);im.pixels.foreach_get(p);p=p.reshape(im.size[1],im.size[0],4);d=[]
for f in ob.data.polygons:
 for li in f.loop_indices:
  v=ob.data.vertices[ob.data.loops[li].vertex_index];x,y,z=v.co
  if x<.44 or z>1.075:continue
  uv=ob.data.uv_layers.active.data[li].uv;c=p[int(uv.y*4095)%4096,int(uv.x*4095)%4096,:3]
  if c[0]>.40 and c[0]>c[2]*1.10:
   delta=np.array([x-.480,y+.221,z-1.015]);d.append([float(delta@np.array([.76,0,-.65])),float(delta@np.array([.65,0,.76])),float(-delta[1]),*[float(t) for t in v.co]])
a=np.array(d);print('HANDQ',np.quantile(a,[0,.05,.25,.5,.75,.95,1],axis=0).tolist());json.dump(d,open(O+'/hand-points.json','w'))
