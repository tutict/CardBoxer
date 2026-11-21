"""Actual exported normal basis acceptance; missing TANGENT was the observed bug."""
import json,struct,math,sys
from pathlib import Path
import numpy as np
p=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent/'foe-raw.glb'
raw=p.read_bytes();pos=12;doc=None;binary=None
while pos<len(raw):
 n,t=struct.unpack_from('<II',raw,pos);data=raw[pos+8:pos+8+n];pos+=8+n
 if t==0x4e4f534a:doc=json.loads(data)
 if t==0x004e4942:binary=data
def access(i):
 a=doc['accessors'][i];v=doc['bufferViews'][a['bufferView']];dt={5126:'<f4',5123:'<u2',5125:'<u4',5121:'u1'}[a['componentType']];w={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']];size=np.dtype(dt).itemsize;stride=v.get('byteStride',w*size)
 return np.ndarray((a['count'],w),dtype=dt,buffer=binary,offset=v.get('byteOffset',0)+a.get('byteOffset',0),strides=(stride,size)).copy()
prims=[p for m in doc['meshes'] for p in m['primitives']]
assert len(prims)==1,'one runtime primitive required'
p=prims[0];a=p['attributes'];assert 'TANGENT' in a,'RED: runtime normal map has no exported TANGENT'
t=access(a['TANGENT']);n=access(a['NORMAL']);uv=access(a['TEXCOORD_0']);w=access(a['WEIGHTS_0'])
assert np.isfinite(t).all() and np.isfinite(n).all() and np.isfinite(uv).all() and np.isfinite(w).all()
assert np.max(np.abs(np.linalg.norm(t[:,:3],axis=1)-1))<1e-4,'tangent must be unit length'
assert np.max(np.abs((t[:,:3]*n).sum(axis=1)))<1e-4,'tangent must be orthogonal to normal'
assert np.max(np.abs(np.abs(t[:,3])-1))<1e-6,'tangent handedness must be +/-1'
assert np.max(np.abs(w.sum(axis=1)-1))<1e-4
assert 'TEXCOORD_1' not in a
print(json.dumps({'result':'PASS','vertices':len(t),'triangles':len(access(p['indices']))//3,'tangent_unit_error':float(np.max(np.abs(np.linalg.norm(t[:,:3],axis=1)-1))),'orthogonality_error':float(np.max(np.abs((t[:,:3]*n).sum(axis=1))))}))
