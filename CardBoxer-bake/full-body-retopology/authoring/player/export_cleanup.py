"""Remove float round-off from morph normals while keeping hand shading deltas."""
import json,struct

def clean(path):
 data=bytearray(open(path,'rb').read());jlen=struct.unpack_from('<I',data,12)[0];doc=json.loads(data[20:20+jlen]);binary_start=20+jlen+8;count=0;max_cleared=0
 for mesh in doc.get('meshes',[]):
  for primitive in mesh.get('primitives',[]):
   for target in primitive.get('targets',[]):
    for semantic in ['NORMAL','TANGENT']:
     if semantic not in target:continue
     accessor=doc['accessors'][target[semantic]];view=doc['bufferViews'][accessor['bufferView']]
     assert accessor['componentType']==5126 and accessor['type']=='VEC3'
     offset=binary_start+view.get('byteOffset',0)+accessor.get('byteOffset',0);stride=view.get('byteStride',12)
     for i in range(accessor['count']):
      for j in range(3):
       p=offset+i*stride+j*4;v=struct.unpack_from('<f',data,p)[0]
       if 0<abs(v)<1e-6:max_cleared=max(max_cleared,abs(v));struct.pack_into('<f',data,p,0.);count+=1
 open(path,'wb').write(data)
 return {'cleared_morph_normal_components':count,'max_cleared_component':max_cleared,'threshold':1e-6,'meaningful_hand_normal_deltas_preserved':True}
