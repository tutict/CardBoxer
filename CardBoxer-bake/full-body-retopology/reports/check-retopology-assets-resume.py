"""Read-only acceptance gates for canonical character retopology GLBs."""
from __future__ import annotations
import argparse
import json
import struct
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from canonical_glb import GLB, SHAPES, sha256, skin_rest_vertices, transform_points


def image_dimensions(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16]==b"IHDR": return list(struct.unpack_from(">II",data,16))
    raise ValueError("PBR atlas must be a PNG with IHDR")


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


def check_asset(source_glb: Path, candidate_glb: Path, profile_json: Path|None=None) -> dict:
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
        indices=g.accessor(p["indices"]).astype(int).ravel()
    except Exception as exc: error("accessors",exc);return result
    metrics=result["metrics"];metrics.update(vertices=len(pos),triangles=len(indices)//3,joints=len(names),surfaces=1,materials=len(d.get("materials",[])))
    if len(indices)%3 or np.any(indices<0) or np.any(indices>=len(pos)): error("triangle_indices","Invalid triangle indices");return result
    if len(indices)//3>80000: error("triangle_budget",f"{len(indices)//3} exceeds 80000")
    if len(pos)==0: error("empty_geometry","No vertices");return result
    if normal.shape!=pos.shape or np.max(np.abs(np.linalg.norm(normal,axis=1)-1))>.01: error("normal_length","Vertex normals must be finite unit vectors")
    tri=pos[indices.reshape(-1,3)];areas=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)*.5
    metrics["degenerate_triangles"]=int(np.sum(areas<1e-12))
    if metrics["degenerate_triangles"]: error("degenerate_triangles",metrics["degenerate_triangles"])
    if joints.shape!=(len(pos),4) or weights.shape!=(len(pos),4): error("four_influences","Exactly JOINTS_0/WEIGHTS_0 VEC4 required");return result
    if np.any(joints<0) or np.any(joints>=len(names)): error("joint_range","Out of range JOINTS_0");return result
    weights_error=float(np.max(np.abs(weights.sum(axis=1)-1)));metrics["weight_sum_error"]=weights_error
    if np.any(weights<0) or weights_error>1e-5: error("normalized_weights",weights_error)
    for key,value in a.items():
        if key.startswith("WEIGHTS_") and key!="WEIGHTS_0" and np.any(g.accessor(value)>1e-7): error("four_influences",key)
    neutral=names.index("neutral_bone") if "neutral_bone" in names else -1
    neutral_max=float(np.max(np.where(joints==neutral,weights,0)));metrics["neutral_max_weight"]=neutral_max
    if neutral_max>1e-7: error("neutral_influence",neutral_max)
    world=transform_points(g.globals()[g.mesh_node()],pos)
    metrics["rest_bind_error_m"]=float(np.linalg.norm(skin_rest_vertices(g)-world,axis=1).max())
    if metrics["rest_bind_error_m"]>1e-5: error("rest_deformation",metrics["rest_bind_error_m"])
    original_pos=src.accessor(sp["attributes"]["POSITION"])
    unchanged=(pos.shape==original_pos.shape and np.array_equal(pos.astype(np.float32),original_pos) and np.array_equal(indices,src.accessor(sp["indices"]).ravel()))
    if unchanged: error("new_geometry","Candidate still contains the original indexed geometry")
    source_world=transform_points(src.globals()[src.mesh_node()],original_pos)
    metrics["sole_y_deviation_m"]=float(abs(world[:,1].min()-source_world[:,1].min()))
    if metrics["sole_y_deviation_m"]>.02: error("sole_deviation",metrics["sole_y_deviation_m"])
    # Source-bound hand envelope: distal forearm region and its own forearm group.
    # This excludes every boot/body vertex and the opposing hand, while allowing
    # new fingers/UV seams and changed vertex counts without authored index masks.
    hand_masks={};globals_=g.globals();source_globals=src.globals();source_joints=src.skin()["joints"]
    for side,bone in (("front","forearm_f"),("rear","forearm_b")):
        if bone not in names: continue
        idx=names.index(bone);own=np.sum(weights*(joints==idx),axis=1)
        local=transform_points(np.linalg.inv(globals_[g.skin()["joints"][idx]]),world)
        source_i=source_joints[original_names.index(bone)]
        parent_name=bone.replace("forearm","upperarm");parent_i=source_joints[original_names.index(parent_name)]
        upper_length=np.linalg.norm(source_globals[source_i][:3,3]-source_globals[parent_i][:3,3])
        hand_masks[side]=(own>=.25)&(local[:,1]>=upper_length*.55)
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
        delta=g.accessor(target["POSITION"]).astype(float)
        if delta.shape!=pos.shape: error("morph_count",name);continue
        morphs[name]=delta;active=np.linalg.norm(delta,axis=1)>1e-8
        side="front" if name.endswith("_f") else "rear";mask=hand_masks.get(side,np.zeros(len(pos),bool))
        for semantic,accessor in target.items():
            values=g.accessor(accessor)
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


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_glb",type=Path);parser.add_argument("candidate_glb",type=Path)
    parser.add_argument("--profile",type=Path);parser.add_argument("--report",type=Path)
    args=parser.parse_args();report=check_asset(args.source_glb,args.candidate_glb,args.profile)
    if args.report: args.report.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2));return 0 if report["ok"] else 1


if __name__=="__main__": raise SystemExit(main())
