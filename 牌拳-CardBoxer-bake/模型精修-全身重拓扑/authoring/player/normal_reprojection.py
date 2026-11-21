"""Bake high reference shading into the low atlas without ray misses.

Body detail uses source normal texture in its original tangent basis, adjusted
by the refined high geometric normal. New fingers use subdivided high geometry.
Every written texel is encoded in the new low UV tangent basis.
"""
import bpy,bmesh,numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

def unit(v):
 n=np.linalg.norm(v,axis=-1,keepdims=True)
 return v/np.maximum(n,1e-12)

def bary(p,a,b,c):
 d=b-a;e=c-a;q=p-a;den=d.dot(d)*e.dot(e)-d.dot(e)**2
 if abs(den)<1e-16:return np.array([1.,0.,0.])
 v=(e.dot(e)*q.dot(d)-d.dot(e)*q.dot(e))/den
 w=(d.dot(d)*q.dot(e)-d.dot(e)*q.dot(d))/den
 r=np.maximum([1-v-w,v,w],0);return r/r.sum()

def reference(mesh,tangent=False):
 mesh.calc_loop_triangles()
 if tangent:mesh.calc_tangents(uvmap=mesh.uv_layers.active.name)
 tris=list(mesh.loop_triangles);coords=[v.co.copy() for v in mesh.vertices]
 normals=np.array([tuple(n.vector) for n in mesh.corner_normals])
 tree=BVHTree.FromPolygons(coords,[tuple(t.vertices) for t in tris],all_triangles=True)
 return mesh,tris,coords,normals,tree

def nearest(ref,p):
 mesh,tris,coords,normals,tree=ref;q,n,idx,dist=tree.find_nearest(Vector(p));tr=tris[idx]
 weights=bary(q,*[coords[i] for i in tr.vertices]);normal=unit(weights@normals[list(tr.loops)])
 return normal,tr,weights

def bake(low,source,high,highhand,body_count,path):
 size=4096;me=low.data.copy();bm=bmesh.new();bm.from_mesh(me);bmesh.ops.triangulate(bm,faces=[f for f in bm.faces if len(f.verts)>4]);bm.to_mesh(me);bm.free();me.update();me.calc_loop_triangles();me.calc_tangents(uvmap='Retopology_4K_Atlas')
 src=reference(source.data,True);hi=reference(high.data);hand=reference(highhand.data)
 snorm=bpy.data.images.load(path.replace('/authoring/player/textures/player-normal-4k.png','/baseline/assets/3d/player-rigged_texture_pbr_20250901_normal.png'),check_existing=True)
 snorm.colorspace_settings.name='Non-Color';sp=np.empty(len(snorm.pixels),np.float32);snorm.pixels.foreach_get(sp);sp=sp.reshape(snorm.size[1],snorm.size[0],4)
 pixels=np.zeros((size,size,4),np.float32);pixels[:]=(.5,.5,1,1);filled=np.zeros((size,size),bool)
 normals=np.array([tuple(n.vector) for n in me.corner_normals]);tangents=np.array([tuple(l.tangent) for l in me.loops]);signs=np.array([l.bitangent_sign for l in me.loops]);uvl=me.uv_layers['Retopology_4K_Atlas']
 count=0;bad=0
 for ti,tr in enumerate(me.loop_triangles):
  uv=np.array([tuple(uvl.data[l].uv) for l in tr.loops])*size
  xmin=max(0,int(np.floor(uv[:,0].min())));xmax=min(size-1,int(np.ceil(uv[:,0].max())));ymin=max(0,int(np.floor(uv[:,1].min())));ymax=min(size-1,int(np.ceil(uv[:,1].max())))
  if xmax<xmin or ymax<ymin:continue
  xx,yy=np.meshgrid(np.arange(xmin,xmax+1)+.5,np.arange(ymin,ymax+1)+.5);d=uv[1]-uv[0];e=uv[2]-uv[0];det=d[0]*e[1]-d[1]*e[0]
  if abs(det)<1e-10:bad+=1;continue
  px=xx-uv[0,0];py=yy-uv[0,1];b=(px*e[1]-py*e[0])/det;c=(d[0]*py-d[1]*px)/det;a=1-b-c;ok=(a>=-1e-6)&(b>=-1e-6)&(c>=-1e-6)
  ys,xs=np.nonzero(ok);xs+=xmin;ys+=ymin
  if not len(xs):continue
  weights=np.array([a[ok],b[ok],c[ok]]).T;coords=np.array([tuple(me.vertices[i].co) for i in tr.vertices]);points=weights@coords;world=[]
  authored=all(i>=body_count for i in tr.vertices)
  for p in points:
   if authored:wn,_,_=nearest(hand,p)
   else:
    n,st,sw=nearest(src,p);smesh=source.data;uv=sw@np.array([tuple(smesh.uv_layers.active.data[l].uv) for l in st.loops]);sx=min(sp.shape[1]-1,max(0,int(uv[0]*sp.shape[1])));sy=min(sp.shape[0]-1,max(0,int(uv[1]*sp.shape[0])))
    tn=unit(sw@np.array([tuple(smesh.loops[l].tangent) for l in st.loops]));tn=unit(tn-n*np.dot(tn,n));sg=1 if sum(sw[j]*smesh.loops[l].bitangent_sign for j,l in enumerate(st.loops))>=0 else -1;bn=np.cross(n,tn)*sg
    m=sp[sy,sx,:3]*2-1;wn=unit(tn*m[0]+bn*m[1]+n*m[2])
    hn,_,_=nearest(hi,p)
    # Preserve source costume custom shading; refined high skin supplies its
    # real local geometric correction where the high sculpt was edited.
    if abs(p[0])<.092 and 1.44<p[2]<1.558 and p[1]<-.25:wn=unit(wn+(hn-n)*.35)
   world.append(wn)
  world=np.array(world);n=unit(weights@normals[list(tr.loops)]);t=unit(weights@tangents[list(tr.loops)]);t=unit(t-n*np.sum(t*n,axis=1,keepdims=True));sg=np.where(weights@signs[list(tr.loops)]>=0,1.,-1.);bt=np.cross(n,t)*sg[:,None]
  encoded=unit(np.column_stack((np.sum(world*t,axis=1),np.sum(world*bt,axis=1),np.sum(world*n,axis=1))))*.5+.5
  pixels[ys,xs,:3]=encoded;filled[ys,xs]=True;count+=len(xs)
  if ti%8000==0:print('PLAYER normal_reference_bake',ti,'texels',count,flush=True)
 for _ in range(16):
  nxt=filled.copy()
  for dy,dx in [(1,0),(-1,0),(0,1),(0,-1)]:
   shifted=np.roll(filled,(dy,dx),(0,1));mask=shifted&~nxt;pixels[mask]=np.roll(pixels,(dy,dx),(0,1))[mask];nxt|=shifted
  filled=nxt
 im=bpy.data.images.new('player-normal-4k',width=size,height=size,alpha=True);im.colorspace_settings.name='Non-Color';im.pixels.foreach_set(pixels.ravel());im.filepath_raw=path;im.file_format='PNG';im.save()
 print('PLAYER normal_reference_bake_complete',count,'degenerate_uv_triangles',bad,flush=True)
 return im,{'filled_texels_before_dilation':count,'degenerate_uv_triangles':bad,'method':'source tangent shading + refined high skin geometric correction + subdivided high hand normals, encoded in new low UV tangent basis; no projection rays'}
