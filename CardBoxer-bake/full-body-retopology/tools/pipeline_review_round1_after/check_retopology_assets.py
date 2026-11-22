"""Read-only acceptance gates for canonical character retopology GLBs."""
from __future__ import annotations
import argparse
import json
import struct
import sys
import zlib
from functools import lru_cache
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from canonical_glb import GLB, SHAPES, sha256, skin_rest_vertices, transform_points,validate_output_paths,atomic_write


@lru_cache(maxsize=12)
def image_dimensions(data):
    """Check PNG integrity and complete scanline payload, not just its header."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):raise ValueError("PBR atlas must be PNG")
    off=8;header=None;compressed=bytearray();ended=False;idat_seen=False;idat_closed=False;palette=False;transparency=False
    while off<len(data):
        if off+12>len(data):raise ValueError("Truncated PNG chunk")
        count=struct.unpack_from(">I",data,off)[0];kind=data[off+4:off+8];end=off+8+count
        if end+4>len(data):raise ValueError("Truncated PNG payload")
        payload=data[off+8:end]
        if any(not (65<=letter<=90 or 97<=letter<=122) for letter in kind) or kind[2]&32:
            raise ValueError("Invalid PNG chunk type")
        if zlib.crc32(kind+payload)!=struct.unpack_from(">I",data,end)[0]:raise ValueError("PNG CRC mismatch")
        if header is None and kind!=b"IHDR":raise ValueError("PNG IHDR must be first")
        if idat_seen and kind!=b"IDAT":idat_closed=True
        if kind==b"IHDR":
            if header is not None or count!=13:raise ValueError("Invalid PNG IHDR")
            header=struct.unpack(">IIBBBBB",payload)
            if header[3] not in (2,6) or header[2] not in (8,16):
                raise ValueError("PBR atlas PNG supports RGB/RGBA at 8/16 bits only")
        elif kind==b"PLTE":
            if palette or transparency or idat_seen or count<3 or count>768 or count%3:raise ValueError("Invalid PNG palette/order")
            palette=True
        elif kind==b"tRNS":
            if transparency or idat_seen or header[3]!=2 or count!=6:raise ValueError("Invalid PNG transparency/order")
            if max(struct.unpack(">3H",payload))>2**header[2]-1:raise ValueError("PNG transparent sample out of range")
            transparency=True
        elif kind==b"IDAT":
            if idat_closed:raise ValueError("PNG IDAT chunks must be consecutive")
            idat_seen=True;compressed.extend(payload)
        elif kind==b"IEND":
            if count or end+4!=len(data):raise ValueError("Invalid PNG end")
            ended=True;break
        elif not kind[0]&32:raise ValueError("Unsupported critical PNG chunk")
        off=end+4
    if not header or not ended or not compressed:raise ValueError("Incomplete PNG")
    width,height,depth,colour,compression,filtering,interlace=header
    channels={2:3,6:4}.get(colour)
    allowed={2:(8,16),6:(8,16)}
    if not channels or depth not in allowed[colour] or compression or filtering or interlace not in (0,1) or min(width,height)<1 or max(width,height)>4096:
        raise ValueError("Invalid or oversized PNG encoding")
    passes=[(0,0,1,1)] if not interlace else [(0,0,8,8),(4,0,8,8),(0,4,4,8),(2,0,4,4),(0,2,2,4),(1,0,2,2),(0,1,1,2)]
    rows=[]
    for x,y,dx,dy in passes:
        pw=max(0,(width-x+dx-1)//dx);ph=max(0,(height-y+dy-1)//dy)
        if pw and ph:rows.extend([1+(pw*channels*depth+7)//8]*ph)
    expected=sum(rows);decoder=zlib.decompressobj()
    try:decoded=decoder.decompress(bytes(compressed),expected+1)
    except zlib.error as exc:raise ValueError("Invalid PNG compression") from exc
    if len(decoded)!=expected or not decoder.eof or decoder.unused_data:raise ValueError("PNG scanline payload mismatch")
    cursor=0
    for stride in rows:
        if decoded[cursor]>4:raise ValueError("Invalid PNG row filter")
        cursor+=stride
    return [width,height]


def point_surface_distance(point, triangles):
    """Minimum Euclidean distance to triangles, including interior projections."""
    if len(triangles)==0: return float("inf")
    a,b,c=triangles[:,0],triangles[:,1],triangles[:,2]
    best=np.full(len(a),np.inf)
    for start,end in ((a,b),(b,c),(c,a)):
        e=end-start;t=np.clip(np.sum((point-start)*e,axis=1)/np.maximum(np.sum(e*e,axis=1),1e-30),0,1)
        best=np.minimum(best,np.sum((point-(start+t[:,None]*e))**2,axis=1))
    u=b-a;v=c-a;n=np.cross(u,v);n2=np.sum(n*n,axis=1)
    dist=np.sum((point-a)*n,axis=1)/np.maximum(n2,1e-30)
    projection=point-dist[:,None]*n;q=projection-a
    uu=np.sum(u*u,axis=1);uv=np.sum(u*v,axis=1);vv=np.sum(v*v,axis=1)
    qu=np.sum(q*u,axis=1);qv=np.sum(q*v,axis=1);den=uu*vv-uv*uv
    s=(vv*qu-uv*qv)/np.maximum(den,1e-30);t=(uu*qv-uv*qu)/np.maximum(den,1e-30)
    inside=(s>=0)&(t>=0)&(s+t<=1)&(n2>1e-20)
    best[inside]=np.minimum(best[inside],dist[inside]**2*n2[inside])
    return float(np.sqrt(best.min()))


def _check_asset(source_glb: Path, candidate_glb: Path, profile_json: Path|None=None) -> dict:
    result={"version":1,"source":str(Path(source_glb).resolve()),"candidate":str(Path(candidate_glb).resolve()),"ok":False,"errors":[],"warnings":[],"metrics":{}}
    def error(code,detail): result["errors"].append({"code":code,"detail":str(detail)})
    def warning(code,detail): result["warnings"].append({"code":code,"detail":str(detail)})
    try:
        src=GLB(source_glb);g=GLB(candidate_glb);sp=src.mesh_primitive();p=g.mesh_primitive()
    except Exception as exc:
        error("glb_structure",exc);return result
    d=g.doc;names=g.joint_names();original_names=src.joint_names();a=p["attributes"]
    result.update(source_sha256=sha256(source_glb),candidate_sha256=sha256(candidate_glb))
    if len(d.get("meshes",[]))!=1 or len(d.get("skins",[]))!=1 or len([n for n in d["nodes"] if "mesh" in n])!=1:
        error("single_mesh_skin","Runtime needs exactly one body mesh node and one skin")
    if d["nodes"]!=src.doc["nodes"]: error("canonical_nodes","Names, hierarchy, rest TRS/matrices and mesh/skeleton node transforms must exactly match source")
    if names!=original_names or len(names)!=14: error("joint_declaration",f"Expected all original 14 joints in original order: {names}")
    if g.skin().get("joints")!=src.skin().get("joints"): error("joint_indices","Original skin joint node declaration changed")
    if not np.array_equal(g.ibms(),src.ibms()): error("inverse_bind_matrices","Original IBM values changed")
    if {k:v for k,v in g.skin().items() if k!="inverseBindMatrices"}!={k:v for k,v in src.skin().items() if k!="inverseBindMatrices"}:
        error("skin_metadata","Original skin metadata changed")
    if d.get("scenes")!=src.doc.get("scenes") or d.get("scene")!=src.doc.get("scene"): error("canonical_scene","Original scene root declaration changed")
    if d.get("animations"): error("no_animations","Runtime body quaternion data must remain external")
    if len(d.get("materials",[]))!=1 or p.get("material")!=0: error("single_material","One PBR atlas material at surface 0 required")
    missing=[n for n in ("POSITION","NORMAL","TEXCOORD_0","JOINTS_0","WEIGHTS_0") if n not in a]
    if missing: error("vertex_attributes",missing);return result
    try:
        pos=g.accessor(a["POSITION"]).astype(float);normal=g.accessor(a["NORMAL"]).astype(float)
        joints=g.accessor(a["JOINTS_0"]).astype(int);weights=g.accessor(a["WEIGHTS_0"]).astype(float)
    except Exception as exc: error("accessors",exc);return result
    try:indices=g.triangle_indices(len(pos))
    except Exception as exc:error("triangle_indices",exc);return result
    try:source_indices=src.triangle_indices(src.doc["accessors"][sp["attributes"]["POSITION"]]["count"])
    except Exception as exc:error("triangle_indices",exc);return result
    metrics=result["metrics"];metrics.update(vertices=len(pos),triangles=len(indices)//3,joints=len(names),surfaces=1,materials=len(d.get("materials",[])))
    if len(indices)%3 or np.any(indices<0) or np.any(indices>=len(pos)): error("triangle_indices","Invalid triangle indices");return result
    if len(indices)//3>80000: error("triangle_budget",f"{len(indices)//3} exceeds 80000")
    if len(pos)==0: error("empty_geometry","No vertices");return result
    if normal.shape!=pos.shape or np.max(np.abs(np.linalg.norm(normal,axis=1)-1))>.01: error("normal_length","Vertex normals must be finite unit vectors")
    try:
        uv=g.accessor(a["TEXCOORD_0"])
        if uv.shape!=(len(pos),2) or np.any(uv < -1e-6) or np.any(uv > 1+1e-6):error("atlas_uv","UV0 must be finite VEC2 per vertex within the 0..1 atlas")
        if "TANGENT" not in a:error("tangent_basis","Tangent normal atlas requires an exported UV0 tangent basis")
        else:
            tangent=g.accessor(a["TANGENT"])
            if tangent.shape!=(len(pos),4) or np.max(np.abs(np.linalg.norm(tangent[:,:3],axis=1)-1))>.01 or np.max(np.abs(np.sum(tangent[:,:3]*normal,axis=1)))>.01 or np.any(np.abs(np.abs(tangent[:,3])-1)>1e-5):
                error("tangent_basis","Tangents must be finite unit XYZ perpendicular to normal, W +/-1")
    except Exception as exc:error("tangent_basis",exc)
    tri=pos[indices.reshape(-1,3)];areas=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)*.5
    metrics["degenerate_triangles"]=int(np.sum(areas<1e-12))
    if metrics["degenerate_triangles"]: error("degenerate_triangles",metrics["degenerate_triangles"])
    if joints.shape!=(len(pos),4) or weights.shape!=(len(pos),4): error("four_influences","Exactly JOINTS_0/WEIGHTS_0 VEC4 required");return result
    joint_accessor=d["accessors"][a["JOINTS_0"]]
    if joint_accessor["componentType"] not in (5121,5123) or joint_accessor.get("normalized",False) or joint_accessor["type"]!="VEC4":
        error("joint_format","JOINTS_0 requires unnormalized unsigned byte/short VEC4")
    if np.any(joints<0) or np.any(joints>=len(names)): error("joint_range","Out of range JOINTS_0");return result
    weights_error=float(np.max(np.abs(weights.sum(axis=1)-1)));metrics["weight_sum_error"]=weights_error
    if np.any(weights<0) or weights_error>1e-5: error("normalized_weights",weights_error)
    for key,value in a.items():
        if key.startswith("WEIGHTS_") and key!="WEIGHTS_0" and np.any(np.abs(g.accessor(value))>1e-7): error("four_influences",key)
    neutral=names.index("neutral_bone") if "neutral_bone" in names else -1
    neutral_max=float(np.max(np.where(joints==neutral,weights,0)));metrics["neutral_max_weight"]=neutral_max
    if neutral_max>1e-7: error("neutral_influence",neutral_max)
    world=transform_points(g.globals()[g.mesh_node()],pos)
    metrics["rest_bind_error_m"]=float(np.linalg.norm(skin_rest_vertices(g)-world,axis=1).max())
    if metrics["rest_bind_error_m"]>1e-5: error("rest_deformation",metrics["rest_bind_error_m"])
    original_pos=src.accessor(sp["attributes"]["POSITION"])
    unchanged=(pos.shape==original_pos.shape and np.array_equal(pos.astype(np.float32),original_pos) and np.array_equal(indices,source_indices))
    if unchanged: error("new_geometry","Candidate still contains the original indexed geometry")
    source_world=transform_points(src.globals()[src.mesh_node()],original_pos)
    metrics["sole_y_deviation_m"]=float(abs(world[:,1].min()-source_world[:,1].min()))
    if metrics["sole_y_deviation_m"]>.02: error("sole_deviation",metrics["sole_y_deviation_m"])
    # Source-bound hand envelope: distal forearm region and its own forearm group.
    # This excludes every boot/body vertex and the opposing hand, while allowing
    # new fingers/UV seams and changed vertex counts without authored index masks.
    hand_masks={};globals_=g.globals();source_globals=src.globals();source_joints=src.skin()["joints"]
    source_weights=src.accessor(sp["attributes"]["WEIGHTS_0"]);source_indices=src.accessor(sp["attributes"]["JOINTS_0"])
    for side,bone in (("front","forearm_f"),("rear","forearm_b")):
        if bone not in names: continue
        idx=names.index(bone);own=np.sum(weights*(joints==idx),axis=1)
        local=transform_points(np.linalg.inv(globals_[g.skin()["joints"][idx]]),world)
        source_i=source_joints[original_names.index(bone)]
        source_local=transform_points(np.linalg.inv(source_globals[source_i]),source_world)
        source_own=np.sum(source_weights*(source_indices==original_names.index(bone)),axis=1)
        weighted=source_own>=.25
        # Original forearm geometry determines its distal region. Upperarm length
        # is unrelated to the wrist and falsely rejects the foe's shorter hands.
        distal_start=float(source_local[weighted,1].max())*.5 if weighted.any() else float("inf")
        source_hand=weighted&(source_local[:,1]>=distal_start)
        hand_masks[side]=(own>=.25)&(local[:,1]>=distal_start)
        metrics[side+"_hand_distal_start_local_m"]=distal_start if np.isfinite(distal_start) else None
        if source_hand.any():
            lo=source_local[source_hand].min(axis=0)-.02;hi=source_local[source_hand].max(axis=0)+.02
            hand_masks[side]&=np.all((local>=lo)&(local<=hi),axis=1)
            metrics[side+"_source_hand_bounds_local_m"]=[lo.tolist(),hi.tolist()]
        else:
            hand_masks[side][:]=False
            error("source_hand_bounds",f"No original distal {bone} vertices")
        metrics[side+"_hand_envelope_vertices"]=int(hand_masks[side].sum())
    mesh=d["meshes"][d["nodes"][g.mesh_node()]["mesh"]]
    shape_names=mesh.get("extras",{}).get("targetNames",[]);targets=p.get("targets",[])
    metrics["morph_names"]=shape_names
    if len(shape_names)!=4 or set(shape_names)!=set(SHAPES) or len(targets)!=4: error("required_morphs",f"Expected exact four grip targets; got {shape_names}")
    defaults=mesh.get("weights",[0]*len(targets));node_defaults=d["nodes"][g.mesh_node()].get("weights",defaults)
    if len(defaults)!=len(targets) or any(v!=0 for v in defaults) or any(v!=0 for v in node_defaults): error("morph_defaults","Basis must be open, all morph defaults zero")
    morphs={}
    for name,target in zip(shape_names,targets):
        if "POSITION" not in target: error("morph_position",name);continue
        try:delta=g.accessor(target["POSITION"]).astype(float)
        except Exception as exc:error("morph_accessor",f"{name}.POSITION: {exc}");continue
        if delta.shape!=pos.shape: error("morph_count",name);continue
        morphs[name]=delta;active=np.linalg.norm(delta,axis=1)>1e-8
        side="front" if name.endswith("_f") else "rear";mask=hand_masks.get(side,np.zeros(len(pos),bool))
        for semantic,accessor in target.items():
            try:values=g.accessor(accessor)
            except Exception as exc:error("morph_accessor",f"{name}.{semantic}: {exc}");continue
            if values.shape!=pos.shape:error("morph_count",f"{name}.{semantic}");continue
            affected=np.any(np.abs(values)>1e-8,axis=1)
            if np.any(affected & ~mask): error("morph_hand_only",f"{name}.{semantic}: {int(np.sum(affected & ~mask))} vertices outside its own distal forearm/hand")
        metrics[name+"_active_vertices"]=int(active.sum())
        if not active.any(): error("nonempty_morph",name)
        if np.any(np.linalg.norm(delta,axis=1)>.3): error("morph_spike",name)
    if len(d.get("images",[]))!=3: error("pbr_images","Exactly 3 embedded 4096x4096 PNG atlases required")
    sizes=[]
    for image in d.get("images",[]):
        try:
            if "uri" in image: error("embedded_images",image["uri"]);continue
            size=image_dimensions(g.view(image["bufferView"]));sizes.append(size)
            if size!=[4096,4096]: error("atlas_resolution",size)
        except Exception as exc: error("pbr_image",exc)
    metrics["image_sizes"]=sizes
    if len(d.get("materials",[]))==1:
        m=d["materials"][0];pbr=m.get("pbrMetallicRoughness",{})
        texture_refs=[pbr.get("baseColorTexture"),m.get("normalTexture"),pbr.get("metallicRoughnessTexture")]
        if any(x is None for x in texture_refs): error("pbr_channels","Base color, tangent normal and metallic/roughness textures required")
        else:
            try:
                if any(x.get("texCoord",0)!=0 or x.get("extensions",{}).get("KHR_texture_transform") for x in texture_refs+[m.get("occlusionTexture",{})]):
                    error("pbr_texcoord","All PBR roles must use the authored UV0 atlas without extra texture transforms")
                image_indices=[d["textures"][x["index"]]["source"] for x in texture_refs]
                if len(set(image_indices))!=3: error("pbr_channels","PBR roles must reference three distinct images")
                ao=m.get("occlusionTexture")
                if not ao or d["textures"][ao["index"]]["source"]!=image_indices[2]: error("orm_occlusion","Occlusion must use the same ORM image as metallic/roughness")
            except (KeyError,IndexError) as exc: error("pbr_texture_indices",exc)
    if profile_json is not None:
        try:
            profile=json.loads(Path(profile_json).read_text(encoding="utf-8"))
            if profile.get("version")!=1 or profile.get("role") not in ("player","foe"): raise ValueError("Invalid profile version/role")
            for side,bone,half,full in (("front","forearm_f","grip_half_f","grip_f"),("rear","forearm_b","grip_half_b","grip_b")):
                for state,name in (("open",None),("half",half),("closed",full)):
                    point=np.asarray(profile["hand_sockets"][side][state],dtype=float)
                    if point.shape!=(3,) or not np.isfinite(point).all(): raise ValueError("Socket must be finite VEC3")
                    socket_world=transform_points(globals_[g.skin()["joints"][names.index(bone)]],point)
                    vertices=transform_points(globals_[g.mesh_node()],pos+(morphs[name] if name else 0))
                    hand_tris=np.any(hand_masks[side][indices.reshape(-1,3)],axis=1)
                    distance=point_surface_distance(socket_world,vertices[indices.reshape(-1,3)[hand_tris]])
                    metrics[side+"_"+state+"_socket_surface_error_m"]=distance
                    if distance>.02: error("socket_surface",f"{side}.{state}: {distance:.6f}m")
        except Exception as exc: error("profile",exc)
    else: warning("profile_unchecked","Supply --profile to verify contact sockets on open/half/closed geometry")
    warning("visual_runtime_required","Surface openings, silhouette, all19 clips/both facings and render performance require the root's visual/runtime acceptance")
    result["ok"]=not result["errors"]
    return result


def check_asset(source_glb: Path, candidate_glb: Path, profile_json: Path|None=None) -> dict:
    """Malformed input is a failed gate with diagnostics, never an uncaught crash."""
    try:return _check_asset(source_glb,candidate_glb,profile_json)
    except (ValueError,KeyError,IndexError,TypeError,OSError,struct.error,np.linalg.LinAlgError) as exc:
        return {"version":1,"source":str(Path(source_glb).resolve()),"candidate":str(Path(candidate_glb).resolve()),
                "ok":False,"errors":[{"code":"malformed_asset","detail":str(exc)}],"warnings":[],"metrics":{}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_glb",type=Path);parser.add_argument("candidate_glb",type=Path)
    parser.add_argument("--profile",type=Path);parser.add_argument("--report",type=Path)
    args=parser.parse_args()
    if args.report:
        inputs={args.source_glb,args.candidate_glb,Path(__file__),Path(__file__).with_name("canonical_glb.py")}
        if args.profile:inputs.add(args.profile)
        for path in (args.source_glb,args.candidate_glb):
            inputs|=GLB(path).input_files()
        validate_output_paths(inputs,(args.report,))
    report=check_asset(args.source_glb,args.candidate_glb,args.profile)
    if args.report:atomic_write(args.report,(json.dumps(report,indent=2)+"\n").encode("utf-8"))
    print(json.dumps(report,indent=2));return 0 if report["ok"] else 1


if __name__=="__main__": raise SystemExit(main())
