"""Canonical GLB bridge: new geometry, original rest hierarchy and binding basis.

Run with Blender 5.2's bundled Python, or any Python with NumPy. No bpy required.
The canonicalize API deliberately does not enforce morph/PBR acceptance, allowing
an unedited Blender roundtrip to test the bridge independently of new authoring.
Use check_retopology_assets.py for delivery acceptance.
"""
from __future__ import annotations
import argparse
import base64
import copy
import hashlib
import json
import math
import os
import struct
import tempfile
from pathlib import Path
from urllib.parse import unquote,urlsplit
import numpy as np

DTYPES = {5120:"i1",5121:"u1",5122:"<i2",5123:"<u2",5125:"<u4",5126:"<f4"}
WIDTH = {"SCALAR":1,"VEC2":2,"VEC3":3,"VEC4":4,"MAT2":4,"MAT3":9,"MAT4":16}
SHAPES = ("grip_half_f","grip_f","grip_half_b","grip_b")


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def integer(value, label, minimum=0):
    if not isinstance(value,int) or isinstance(value,bool) or value<minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def validate_output_paths(inputs,outputs):
    inputs={Path(p).resolve() for p in inputs};outputs=[Path(p).resolve() for p in outputs]
    baseline=Path(__file__).resolve().parent.parent/"baseline"
    def same(a,b):
        return a==b or (a.exists() and b.exists() and os.path.samefile(a,b))
    for i,path in enumerate(outputs):
        if path.is_relative_to(baseline):raise ValueError("Frozen baseline write prohibited")
        if any(same(path,p) for p in inputs) or any(same(path,p) for p in outputs[:i]):
            raise ValueError("Input/dependency/output overwrite is prohibited")


def atomic_write(path,payload):
    path=Path(path).resolve();path.parent.mkdir(parents=True,exist_ok=True)
    descriptor,name=tempfile.mkstemp(prefix="."+path.name+".",suffix=".tmp",dir=path.parent)
    temporary=Path(name)
    try:
        with os.fdopen(descriptor,"wb") as stream:
            stream.write(payload);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary.exists():temporary.unlink()


class GLB:
    def __init__(self, path: Path):
        self.path = Path(path).resolve()
        data = self.path.read_bytes()
        if len(data)<20 or struct.unpack_from("<III",data) != (0x46546c67,2,len(data)):
            raise ValueError(f"Invalid glTF 2 GLB header: {self.path}")
        chunks=[]; off=12
        while off < len(data):
            n,kind=struct.unpack_from("<II",data,off); off+=8
            if off+n>len(data): raise ValueError("Truncated GLB chunk")
            chunks.append((kind,data[off:off+n]));off+=n
        if chunks[0][0]!=0x4e4f534a: raise ValueError("GLB JSON must be first")
        self.doc=json.loads(chunks[0][1])
        bins=[b for kind,b in chunks if kind==0x004e4942]
        self.buffers=[]
        for i,buf in enumerate(self.doc.get("buffers",[])):
            uri=buf.get("uri")
            if uri:
                b=self.resource_bytes(uri)
            elif i==0 and bins: b=bins[0]
            else: raise ValueError("Missing buffer payload")
            length=integer(buf["byteLength"],"buffer byteLength",1)
            if len(b)<length: raise ValueError("Truncated buffer")
            self.buffers.append(b[:length])

    def resource_path(self,uri):
        if not isinstance(uri,str):raise ValueError("Resource URI must be a string")
        if uri.startswith("data:"):return None
        if Path(uri).is_absolute():return Path(uri).resolve()
        parsed=urlsplit(uri)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:raise ValueError("Only local file or data resource URIs are supported")
        return (self.path.parent/unquote(parsed.path)).resolve()

    def resource_bytes(self,uri):
        path=self.resource_path(uri)
        if path is not None:return path.read_bytes()
        try:
            header,payload=uri.split(",",1)
            if not header.endswith(";base64"):raise ValueError("Embedded resources must use base64")
            return base64.b64decode(payload,validate=True)
        except (ValueError,base64.binascii.Error) as exc:raise ValueError("Invalid data resource") from exc

    def input_files(self):
        paths={self.path}
        for item in self.doc.get("buffers",[])+self.doc.get("images",[]):
            if "uri" in item:
                path=self.resource_path(item["uri"])
                if path is not None:paths.add(path)
        return paths

    def _view_layout(self,index):
        index=integer(index,"bufferView index")
        if index>=len(self.doc.get("bufferViews",[])):raise ValueError("bufferView index out of range")
        v=self.doc["bufferViews"][index];buffer=integer(v["buffer"],"bufferView buffer index")
        if buffer>=len(self.buffers):raise ValueError("bufferView buffer index out of range")
        start=integer(v.get("byteOffset",0),"bufferView byteOffset");length=integer(v["byteLength"],"bufferView byteLength",1)
        if start+length>len(self.buffers[buffer]):raise ValueError("bufferView crosses buffer boundary")
        return v,self.buffers[buffer],start,length

    def view(self,index):
        v,buffer,start,length=self._view_layout(index)
        return buffer[start:start+length]

    def _read_view(self,index,offset,count,kind,dtype,sparse=False):
        v,buffer,start,length=self._view_layout(index);offset=integer(offset,"accessor byteOffset")
        rows=int(kind[-1]) if kind.startswith("MAT") else WIDTH[kind];columns=rows if kind.startswith("MAT") else 1
        column_stride=((rows*dtype.itemsize+3)//4)*4 if columns>1 else rows*dtype.itemsize
        element_size=columns*column_stride;extent=(columns-1)*column_stride+rows*dtype.itemsize
        if sparse and ("byteStride" in v or "target" in v):raise ValueError("Sparse bufferView cannot declare stride or target")
        stride=integer(v.get("byteStride",element_size),"accessor stride",1)
        if "byteStride" in v and (stride<4 or stride>252 or stride%4 or stride<element_size):
            raise ValueError("Invalid bufferView byteStride")
        if offset%dtype.itemsize or (start+offset)%dtype.itemsize or (columns>1 and (start+offset)%4):
            raise ValueError("Accessor component/matrix alignment violated")
        if offset+(count-1)*stride+extent>length:raise ValueError("Accessor crosses its declared bufferView boundary")
        return np.ndarray((count,columns,rows),dtype=dtype,buffer=buffer,offset=start+offset,
                          strides=(stride,column_stride,dtype.itemsize)).reshape(count,-1).copy()

    def accessor(self, index: int) -> np.ndarray:
        index=integer(index,"accessor index")
        if index>=len(self.doc.get("accessors",[])):raise ValueError("Accessor index out of range")
        a=self.doc["accessors"][index];kind=a["type"];w=WIDTH[kind];dtype=np.dtype(DTYPES[a["componentType"]])
        count=integer(a["count"],"accessor count",1)
        if "bufferView" in a:
            out=self._read_view(a["bufferView"],a.get("byteOffset",0),count,kind,dtype)
        else:
            if a.get("byteOffset",0)!=0:raise ValueError("Accessor without bufferView cannot have byteOffset")
            out=np.zeros((count,w),dtype=dtype)
        if "sparse" in a:
            s=a["sparse"];ia=s["indices"];va=s["values"]
            sparse_count=integer(s["count"],"sparse count",1)
            if sparse_count>count or ia["componentType"] not in (5121,5123,5125):raise ValueError("Invalid sparse count/index storage")
            indices=self._read_view(ia["bufferView"],ia.get("byteOffset",0),sparse_count,"SCALAR",np.dtype(DTYPES[ia["componentType"]]),sparse=True).ravel()
            if np.any(indices>=count) or np.any(indices[1:]<=indices[:-1]):raise ValueError("Sparse indices must be ordered unique and in range")
            values=self._read_view(va["bufferView"],va.get("byteOffset",0),sparse_count,kind,dtype,sparse=True)
            out[indices]=values
        if a.get("normalized") and a["componentType"] != 5126:
            info=np.iinfo(dtype);out=np.maximum(out.astype(np.float64)/info.max,-1.) if info.min<0 else out.astype(np.float64)/info.max
        if not np.isfinite(out).all(): raise ValueError(f"Nonfinite accessor {index}")
        return out

    def mesh_node(self):
        nodes=[i for i,n in enumerate(self.doc.get("nodes",[])) if "mesh" in n and "skin" in n]
        if len(nodes)!=1: raise ValueError(f"Expected one skinned mesh node, found {len(nodes)}")
        return nodes[0]

    def mesh_primitive(self):
        n=self.doc["nodes"][self.mesh_node()];mesh=self.doc["meshes"][n["mesh"]]
        if len(mesh["primitives"])!=1: raise ValueError("Expected one mesh primitive/surface")
        p=mesh["primitives"][0]
        if p.get("mode",4)!=4: raise ValueError("Expected triangles")
        if any(x in p.get("extensions",{}) for x in ("KHR_draco_mesh_compression","EXT_meshopt_compression")):
            raise ValueError("Compressed geometry must be decoded before canonicalization")
        return p

    def triangle_indices(self, vertex_count):
        index=self.mesh_primitive().get("indices")
        if not isinstance(index,int) or isinstance(index,bool) or not 0<=index<len(self.doc["accessors"]):
            raise ValueError("Invalid triangle index accessor")
        a=self.doc["accessors"][index]
        if a["type"]!="SCALAR" or a["componentType"] not in (5121,5123,5125) or a.get("normalized",False) is not False:
            raise ValueError("Invalid triangle storage: unnormalized unsigned SCALAR required")
        values=self.accessor(index).reshape(-1).astype(np.int64)
        if not len(values) or len(values)%3 or np.any(values>=vertex_count):
            raise ValueError("Invalid triangle count or vertex range")
        return values

    def skin(self):
        return self.doc["skins"][self.doc["nodes"][self.mesh_node()]["skin"]]

    def joint_names(self):
        return [self.doc["nodes"][i].get("name","") for i in self.skin()["joints"]]

    def globals(self):
        nodes=self.doc["nodes"];parents={}
        for i,node in enumerate(nodes):
            for child in node.get("children",[]):
                if child in parents: raise ValueError("Node has multiple parents")
                parents[child]=i
        cache={};visiting=set()
        def get(i):
            if i in visiting: raise ValueError("Cyclic node hierarchy")
            if i not in cache:
                visiting.add(i);local=node_matrix(nodes[i])
                cache[i]=(get(parents[i]) @ local) if i in parents else local
                visiting.remove(i)
            return cache[i]
        return [get(i) for i in range(len(nodes))]

    def ibms(self):
        s=self.skin()
        return self.accessor(s["inverseBindMatrices"]).reshape(-1,4,4).transpose(0,2,1) if "inverseBindMatrices" in s else np.repeat(np.eye(4)[None],len(s["joints"]),axis=0)


def node_matrix(node):
    if "matrix" in node: return np.asarray(node["matrix"],dtype=np.float64).reshape(4,4).T
    x,y,z,w=node.get("rotation",[0,0,0,1]);s=node.get("scale",[1,1,1])
    q=np.asarray([x,y,z,w],float);length=np.linalg.norm(q)
    if length<1e-12: raise ValueError("Zero quaternion")
    x,y,z,w=q/length
    m=np.eye(4);m[:3,:3]=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
        [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
        [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]]) @ np.diag(s)
    m[:3,3]=node.get("translation",[0,0,0]);return m


def transform_points(matrix, points):
    return np.asarray(points,dtype=np.float64) @ matrix[:3,:3].T + matrix[:3,3]


def normalized(v):
    lengths=np.linalg.norm(v,axis=1,keepdims=True)
    if np.any(lengths<1e-12): raise ValueError("Zero length direction")
    return v/lengths


class Builder:
    def __init__(self, raw: GLB):
        if len(raw.buffers)!=1: raise ValueError("Expected one GLB buffer")
        self.doc=copy.deepcopy(raw.doc);self.bin=bytearray(raw.buffers[0])

    def view(self, data, target=None):
        self.bin.extend(b"\0"*((-len(self.bin))%4));idx=len(self.doc.setdefault("bufferViews",[]))
        v={"buffer":0,"byteOffset":len(self.bin),"byteLength":len(data)}
        if target: v["target"]=target
        self.doc["bufferViews"].append(v);self.bin.extend(data);return idx

    def accessor(self, values, kind, component=5126, bounds=False):
        a=np.ascontiguousarray(values,dtype=DTYPES[component]);idx=len(self.doc.setdefault("accessors",[]))
        entry={"bufferView":self.view(a.tobytes()),"componentType":component,"count":len(a),"type":kind}
        if bounds: entry.update(min=a.reshape(len(a),-1).min(axis=0).tolist(),max=a.reshape(len(a),-1).max(axis=0).tolist())
        self.doc["accessors"].append(entry);return idx

    def write(self, path):
        self.doc["buffers"]=[{"byteLength":len(self.bin)}]
        j=json.dumps(self.doc,ensure_ascii=True,separators=(",",":"),allow_nan=False).encode();j+=b" "*((-len(j))%4)
        b=bytes(self.bin);b+=b"\0"*((-len(b))%4)
        payload=struct.pack("<III",0x46546c67,2,28+len(j)+len(b))+struct.pack("<II",len(j),0x4e4f534a)+j+struct.pack("<II",len(b),0x004e4942)+b
        atomic_write(path,payload)


def skin_rest_vertices(glb: GLB):
    p=glb.mesh_primitive();attrs=p["attributes"];pos=glb.accessor(attrs["POSITION"]).astype(float)
    joints=glb.accessor(attrs["JOINTS_0"]).astype(int);weights=glb.accessor(attrs["WEIGHTS_0"]).astype(float)
    globals_=glb.globals();palette=np.array([globals_[i] @ ibm for i,ibm in zip(glb.skin()["joints"],glb.ibms())])
    out=np.zeros_like(pos)
    for k in range(4):
        mats=palette[joints[:,k]]
        out+=weights[:,k,None]*(np.einsum("nij,nj->ni",mats[:,:3,:3],pos)+mats[:,:3,3])
    return out


def canonicalize(source_glb: Path, raw_glb: Path, output_glb: Path,
                 sockets_json: Path, profile_json: Path) -> dict:
    paths=[Path(p).resolve() for p in (source_glb,raw_glb,output_glb,sockets_json,profile_json)]
    source_glb,raw_glb,output_glb,sockets_json,profile_json=paths
    validate_output_paths((source_glb,raw_glb,sockets_json,Path(__file__)),(output_glb,profile_json))
    src=GLB(source_glb);raw=GLB(raw_glb);src_prim=src.mesh_primitive();prim=raw.mesh_primitive()
    src.triangle_indices(src.doc["accessors"][src_prim["attributes"]["POSITION"]]["count"])
    input_files=src.input_files()|raw.input_files()|{sockets_json,Path(__file__).resolve()}
    validate_output_paths(input_files,(output_glb,profile_json))
    input_hashes={str(path):sha256(path) for path in sorted(input_files)}
    if len(src.doc["meshes"])!=1 or len(raw.doc["meshes"])!=1 or len(src.doc["skins"])!=1 or len(raw.doc["skins"])!=1:
        raise ValueError("Only a single body mesh and skin may be exported")
    if raw.doc.get("animations"): raise ValueError("Raw animations must not be exported")
    source_names=src.joint_names();raw_names=raw.joint_names()
    if len(source_names)!=14 or "neutral_bone" not in source_names or len(set(source_names))!=14: raise ValueError("Canonical source must declare all 14 unique joints")
    if len(set(raw_names))!=len(raw_names) or set(raw_names)-set(source_names) or (set(source_names)-{"neutral_bone"})-set(raw_names):
        raise ValueError(f"Raw joint names differ from original body: {raw_names}")
    attrs=prim["attributes"]
    for name in ("POSITION","NORMAL","TEXCOORD_0","JOINTS_0","WEIGHTS_0"):
        if name not in attrs: raise ValueError(f"Raw mesh missing {name}")
    joint_accessor=raw.doc["accessors"][attrs["JOINTS_0"]]
    if joint_accessor["componentType"] not in (5121,5123) or joint_accessor.get("normalized",False) or joint_accessor["type"]!="VEC4":
        raise ValueError("JOINTS_0 must use unnormalized unsigned byte/short VEC4 indices")
    joints=raw.accessor(attrs["JOINTS_0"]).astype(np.int64);weights=raw.accessor(attrs["WEIGHTS_0"]).astype(float)
    count=raw.doc["accessors"][attrs["POSITION"]]["count"]
    raw_indices=raw.triangle_indices(count)
    if joints.shape!=(count,4) or weights.shape!=(count,4): raise ValueError("Expected four influences per vertex")
    if np.any(joints<0) or np.any(joints>=len(raw_names)): raise ValueError("Joint index out of range")
    if np.any(weights<0) or np.max(np.abs(weights.sum(axis=1)-1))>0.005: raise ValueError("Raw weights must be normalized and nonnegative")
    for name,acc in attrs.items():
        if name.startswith("WEIGHTS_") and name!="WEIGHTS_0" and np.any(np.abs(raw.accessor(acc))>1e-7): raise ValueError("More than four influences")
    remap=np.array([source_names.index(n) for n in raw_names],dtype=np.uint16);joints=remap[joints]
    if np.any(weights[joints==source_names.index("neutral_bone")]>1e-7): raise ValueError("Neutral bone visible influence prohibited")
    weights/=weights.sum(axis=1,keepdims=True)
    source_globals=src.globals();raw_globals=raw.globals()
    ms=source_globals[src.mesh_node()];mr=raw_globals[raw.mesh_node()]
    raw_rest=skin_rest_vertices(raw);raw_bind=transform_points(mr,raw.accessor(attrs["POSITION"]))
    raw_bind_error=float(np.linalg.norm(raw_rest-raw_bind,axis=1).max())
    if raw_bind_error>1e-5:raise ValueError(f"Raw rest bind error {raw_bind_error:.9g}m exceeds 1e-5m")
    frame=np.linalg.inv(ms) @ mr;linear=frame[:3,:3];normal_matrix=np.linalg.inv(linear).T
    b=Builder(raw);out_prim=b.doc["meshes"][raw.doc["nodes"][raw.mesh_node()]["mesh"]]["primitives"][0]
    out_attrs=out_prim["attributes"]
    positions=transform_points(frame,raw.accessor(attrs["POSITION"]))
    base_normals=raw.accessor(attrs["NORMAL"]).astype(float);new_normals=normalized(base_normals @ normal_matrix.T)
    out_attrs["POSITION"]=b.accessor(positions,"VEC3",bounds=True)
    out_attrs["NORMAL"]=b.accessor(new_normals,"VEC3")
    out_attrs["JOINTS_0"]=b.accessor(joints,"VEC4",5123)
    out_attrs["WEIGHTS_0"]=b.accessor(weights,"VEC4")
    for name in list(out_attrs):
        if name.startswith(("JOINTS_","WEIGHTS_")) and name not in ("JOINTS_0","WEIGHTS_0"): del out_attrs[name]
    if "TANGENT" in attrs:
        t=raw.accessor(attrs["TANGENT"]).astype(float);direction=t[:,:3] @ linear.T
        direction-=new_normals*np.sum(new_normals*direction,axis=1,keepdims=True)
        new_tangents=normalized(direction)
        out_attrs["TANGENT"]=b.accessor(np.c_[new_tangents,t[:,3]*np.sign(np.linalg.det(linear))],"VEC4")
    for original,target in zip(prim.get("targets",[]),out_prim.get("targets",[])):
        if "POSITION" in original: target["POSITION"]=b.accessor(raw.accessor(original["POSITION"]) @ linear.T,"VEC3",bounds=True)
        if "NORMAL" in original:
            normals=normalized((base_normals+raw.accessor(original["NORMAL"])) @ normal_matrix.T)
            target["NORMAL"]=b.accessor(normals-new_normals,"VEC3")
        if "TANGENT" in original:
            if "TANGENT" not in attrs:raise ValueError("Morph tangent needs a base tangent")
            # Tangent XYZ morphs are deltas of normalized directions, just like normals.
            morphed_tangent=(t[:,:3]+raw.accessor(original["TANGENT"])) @ linear.T
            target_normals=normals if "NORMAL" in original else new_normals
            morphed_tangent-=target_normals*np.sum(target_normals*morphed_tangent,axis=1,keepdims=True)
            target["TANGENT"]=b.accessor(normalized(morphed_tangent)-new_tangents,"VEC3")
    if np.linalg.det(linear)<0:
        indices=raw_indices.reshape(-1,3)[:,[0,2,1]].ravel()
        out_prim["indices"]=b.accessor(indices,"SCALAR",5125)
    b.doc["nodes"]=copy.deepcopy(src.doc["nodes"])
    b.doc["skins"]=copy.deepcopy(src.doc["skins"])
    # Preserve IBM payload bit-for-bit; only its accessor index changes.
    b.doc["skins"][0]["inverseBindMatrices"]=b.accessor(src.ibms().transpose(0,2,1).reshape(-1,16),"MAT4")
    for key in ("scenes","scene"):
        if key in src.doc: b.doc[key]=copy.deepcopy(src.doc[key])
        else: b.doc.pop(key,None)
    # Source nodes reference mesh 0. New raw body is required to be the sole mesh.
    for image in b.doc.get("images",[]):
        if "uri" in image:
            uri=image.pop("uri");data=raw.resource_bytes(uri)
            image["bufferView"]=b.view(data);image["mimeType"]="image/png" if data.startswith(b"\x89PNG") else "image/jpeg"
    sockets=json.loads(sockets_json.read_text(encoding="utf-8"))
    if sockets.get("version")!=1 or sockets.get("role") not in ("player","foe") or sockets.get("space")!="blender_world_z_up":
        raise ValueError("Socket schema must be version 1, role player/foe, blender_world_z_up")
    hand_sockets={}
    for side,bone in (("front","forearm_f"),("rear","forearm_b")):
        forearm=source_globals[src.skin()["joints"][source_names.index(bone)]];inv=np.linalg.inv(forearm)
        hand_sockets[side]={}
        for state in ("open","half","closed"):
            point=np.asarray(sockets[side][state],dtype=float)
            if point.shape!=(3,) or not np.isfinite(point).all(): raise ValueError("Socket must be a finite 3-vector")
            yup=np.array([point[0],point[2],-point[1]])
            hand_sockets[side][state]=transform_points(inv,yup).tolist()
    profile={"version":1,"role":sockets["role"],"hand_sockets":hand_sockets}
    b.doc.setdefault("asset",{})["generator"]="CardBoxer canonical GLB bridge v1 (original node/skin basis)"
    b.write(output_glb)
    atomic_write(profile_json,(json.dumps(profile,indent=2,allow_nan=False)+"\n").encode("utf-8"))
    final=GLB(output_glb)
    final_rest=skin_rest_vertices(final)
    final_bind=transform_points(ms,positions)
    report={"version":1,"source":str(source_glb),"raw":str(raw_glb),"output":str(output_glb),
        "source_sha256":input_hashes[str(source_glb)],"raw_sha256":input_hashes[str(raw_glb)],"output_sha256":sha256(output_glb),
        "profile_sha256":sha256(profile_json),"vertices":count,
        "triangles":int(len(raw_indices)//3),"skin_joints":len(source_names),
        "source_mesh_global":ms.tolist(),"raw_mesh_global":mr.tolist(),"raw_to_source_bind":frame.tolist(),
        "raw_rest_bind_error_m":float(np.linalg.norm(raw_rest-raw_bind,axis=1).max()),
        "canonical_rest_bind_error_m":float(np.linalg.norm(final_rest-final_bind,axis=1).max()),
        "world_rest_transfer_error_m":float(np.linalg.norm(final_rest-raw_rest,axis=1).max()),
        "original_nodes_exact":final.doc["nodes"]==src.doc["nodes"],
        "original_ibms_exact":bool(np.array_equal(final.ibms(),src.ibms())),
        "sockets_source":str(sockets_json),"sockets_source_sha256":input_hashes[str(sockets_json)],
        "pipeline_sha256":input_hashes[str(Path(__file__).resolve())],"immutable_input_sha256":input_hashes,
        "joint_remap":{name:source_names.index(name) for name in raw_names},
        "image_sha256":[hashlib.sha256(final.view(im["bufferView"])).hexdigest() for im in final.doc.get("images",[])]}
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("source_glb","raw_glb","output_glb","sockets_json","profile_json"): parser.add_argument(name,type=Path)
    parser.add_argument("--report",type=Path)
    args=parser.parse_args()
    if args.report:
        inputs=GLB(args.source_glb).input_files()|GLB(args.raw_glb).input_files()|{args.sockets_json,Path(__file__)}
        validate_output_paths(inputs,(args.output_glb,args.profile_json,args.report))
    report=canonicalize(args.source_glb,args.raw_glb,args.output_glb,args.sockets_json,args.profile_json)
    if args.report:atomic_write(args.report,(json.dumps(report,indent=2)+"\n").encode("utf-8"))
    print(json.dumps(report,indent=2))


if __name__=="__main__": main()
