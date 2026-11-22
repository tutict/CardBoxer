"""Executable compatibility tests; run with Blender's bundled Python (NumPy)."""
from __future__ import annotations
import copy
import importlib.util
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "baseline/assets/3d"
NAMES = ["hips", "spine", "chest", "neck", "head", "upperarm_b", "forearm_b",
         "upperarm_f", "forearm_f", "thigh_b", "shin_b", "thigh_f", "shin_f", "neutral_bone"]
SHAPES = ["grip_half_f", "grip_f", "grip_half_b", "grip_b"]


def owned_fixture_dir():
    directory=tempfile.TemporaryDirectory(prefix="pipeline_fixture_",dir=HERE)
    if not Path(directory.name).resolve().is_relative_to(HERE.resolve()):
        raise ValueError("Fixture cleanup must stay within owned tools workspace")
    return directory


def read_glb(path):
    b = Path(path).read_bytes()
    n = struct.unpack_from("<I", b, 12)[0]
    d = json.loads(b[20:20+n])
    off = 20+n
    bn = struct.unpack_from("<I", b, off)[0]
    return d, b[off+8:off+8+bn]


def fixture(path, raw=False, body_leak=False):
    """Independent fixture writer: nonidentity mesh frame + reordered raw joints."""
    d = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": 0}],
         "bufferViews": [], "accessors": [], "nodes": [], "scenes": [{"nodes": [14, 15]}],
         "scene": 0, "materials": [{}]}
    blob = bytearray()

    def add(a, kind, component=5126):
        a = np.asarray(a, dtype={5126:"<f4",5123:"<u2"}[component])
        while len(blob) % 4: blob.append(0)
        view = len(d["bufferViews"])
        d["bufferViews"].append({"buffer":0,"byteOffset":len(blob),"byteLength":a.nbytes})
        blob.extend(a.tobytes())
        idx = len(d["accessors"])
        d["accessors"].append({"bufferView":view,"componentType":component,"count":len(a),"type":kind})
        return idx

    for i, name in enumerate(NAMES):
        d["nodes"].append({"name":name, "translation":[0,float(i)/100,0]})
    # Both forearms retain anatomically named parents. Independent neutral root.
    d["nodes"][5]["children"] = [6]
    d["nodes"][7]["children"] = [8]
    d["nodes"].append({"name":"original_rig","children":[i for i in range(14) if i not in (6,8)]})
    if raw:
        # An importer guessed bone basis. It must NEVER become the output basis.
        d["nodes"][6]["rotation"] = [0,0,np.sin(.37),np.cos(.37)]
        mesh_matrix = np.array([[0,-2,0,4],[2,0,0,-1],[0,0,2,.5],[0,0,0,1.]])
    else:
        mesh_matrix = np.array([[0,-1,0,2],[1,0,0,-3],[0,0,1,.2],[0,0,0,1.]])
    d["nodes"].append({"name":"body","mesh":0,"skin":0,"matrix":mesh_matrix.T.ravel().tolist()})
    canonical = np.array([[.1,1.,0],[.2,1.,0],[.1,1.1,0]])
    source_matrix = np.array([[0,-1,0,2],[1,0,0,-3],[0,0,1,.2],[0,0,0,1.]])
    frame = np.linalg.inv(mesh_matrix) @ source_matrix
    p = (np.c_[canonical,np.ones(3)] @ frame.T)[:,:3]
    joint_order = list(reversed(range(13))) if raw else list(range(14))
    joint = joint_order.index(8)
    attrs = {"POSITION":add(p,"VEC3"),"NORMAL":add([[0,0,1]]*3,"VEC3"),
             "TEXCOORD_0":add([[0,0],[1,0],[0,1]],"VEC2"),
             "JOINTS_0":add([[joint,0,0,0]]*3,"VEC4",5123),
             "WEIGHTS_0":add([[1,0,0,0]]*3,"VEC4")}
    prim = {"attributes":attrs,"indices":add([0,1,2],"SCALAR",5123),"material":0}
    if raw:
        morph = (frame[:3,:3] @ np.array([.01,.02,0])).tolist()
        prim["targets"] = [{"POSITION":add([morph]*3 if n.endswith("_f") or n == "grip_f" else [[0,0,0]]*3,"VEC3")} for n in SHAPES]
        if body_leak:
            a = np.array([[joint_order.index(0),0,0,0]]*3,dtype="<u2")
            access = d["accessors"][attrs["JOINTS_0"]]
            view = d["bufferViews"][access["bufferView"]]
            blob[view["byteOffset"]:view["byteOffset"]+a.nbytes] = a.tobytes()
    d["meshes"] = [{"name":"new_topology" if raw else "source_topology","primitives":[prim]}]
    if raw: d["meshes"][0].update(extras={"targetNames":SHAPES},weights=[0]*4)
    # Derive correct raw rest IBMs independently for this hierarchy.
    def global_joint(i):
        m = np.eye(4)
        m[:3,3] = d["nodes"][i]["translation"]
        if i == 6 and raw:
            c,s = np.cos(.74),np.sin(.74)
            m[:3,:3] = [[c,-s,0],[s,c,0],[0,0,1]]
        if i in (6,8):
            parent = np.eye(4); parent[:3,3] = d["nodes"][i-1]["translation"]
            m = parent @ m
        return m
    ibms = np.array([(np.linalg.inv(global_joint(i)) @ mesh_matrix).T.ravel() for i in joint_order])
    d["skins"] = [{"name":"original_rig", "joints":joint_order,"inverseBindMatrices":add(ibms,"MAT4")}]
    d["buffers"][0]["byteLength"] = len(blob)
    j = json.dumps(d,separators=(",",":")).encode(); j += b" "*((-len(j))%4)
    blob += b"\0"*((-len(blob))%4)
    Path(path).write_bytes(struct.pack("<III",0x46546c67,2,28+len(j)+len(blob))+struct.pack("<II",len(j),0x4e4f534a)+j+struct.pack("<II",len(blob),0x004e4942)+blob)
    return canonical


def png_atlas(colour=2,depth=8):
    def chunk(kind, payload):
        return struct.pack(">I",len(payload))+kind+payload+struct.pack(">I",zlib.crc32(kind+payload))
    # Real decodable 4K RGB PNG, not an IHDR-only dimension stub.
    channels={0:1,2:3,3:1,6:4}[colour];pixel=bytes([128])*channels*(depth//8)
    pixels=(b"\0"+pixel*4096)*4096
    return b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",4096,4096,depth,colour,0,0,0))+chunk(b"IDAT",zlib.compress(pixels))+chunk(b"IEND",b"")


def acceptance_pair(directory):
    """Independent three-triangle anatomy: own front/rear hands and boot."""
    from canonical_glb import GLB,Builder
    directory=Path(directory);source=directory/"source.glb";candidate=directory/"candidate.glb"
    fixture(source);b=Builder(GLB(source));b.doc["nodes"][15]["matrix"]=np.eye(4).T.ravel().tolist()
    pos=np.array([[0,.4,0],[.05,.4,0],[0,.45,0],[0,.36,.1],[.05,.36,.1],[0,.41,.1],
                  [0,0,0],[.05,0,0],[0,.05,0]],dtype=float)
    joints=np.array([[8,0,0,0]]*3+[[6,0,0,0]]*3+[[10,0,0,0]]*3)
    attrs={"POSITION":b.accessor(pos,"VEC3",bounds=True),"NORMAL":b.accessor([[0,0,1]]*9,"VEC3"),
           "TEXCOORD_0":b.accessor([[0,0],[1,0],[0,1]]*3,"VEC2"),"TANGENT":b.accessor([[1,0,0,1]]*9,"VEC4"),
           "JOINTS_0":b.accessor(joints,"VEC4",5123),"WEIGHTS_0":b.accessor([[1,0,0,0]]*9,"VEC4")}
    prim={"attributes":attrs,"indices":b.accessor(np.arange(9),"SCALAR",5123),"material":0}
    b.doc["meshes"][0]["primitives"]=[prim]
    ibms=[]
    for i in range(14):
        m=np.eye(4);m[1,3]=-float(i)/100-(float(i-1)/100 if i in (6,8) else 0);ibms.append(m.T.ravel())
    b.doc["skins"][0]["inverseBindMatrices"]=b.accessor(ibms,"MAT4")
    atlas=png_atlas();b.doc["images"]=[{"bufferView":b.view(atlas),"mimeType":"image/png"} for _ in range(3)]
    b.doc["textures"]=[{"source":i} for i in range(3)]
    b.doc["materials"]=[{"pbrMetallicRoughness":{"baseColorTexture":{"index":0},"metallicRoughnessTexture":{"index":2}},
                        "normalTexture":{"index":1},"occlusionTexture":{"index":2}}]
    b.write(source)
    pos[0,0]=.001;prim["attributes"]["POSITION"]=b.accessor(pos,"VEC3",bounds=True)
    prim["targets"]=[]
    for name in SHAPES:
        delta=np.zeros((9,3));delta[:3 if name.endswith("_f") else 0]=[.01,.01,0]
        if name.endswith("_b"):delta[3:6]=[-.01,.01,0]
        if name in ("grip_f","grip_b"):delta*=2
        prim["targets"].append({"POSITION":b.accessor(delta,"VEC3",bounds=True)})
    b.doc["meshes"][0].update(extras={"targetNames":SHAPES},weights=[0]*4)
    b.write(candidate);return source,candidate


class CanonicalTests(unittest.TestCase):
    def module(self, name):
        spec = importlib.util.spec_from_file_location(name,HERE/(name+".py"))
        self.assertTrue(spec and spec.loader and Path(spec.origin).is_file(), "missing canonical pipeline API")
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        return mod

    @unittest.expectedFailure
    def test_original_acceptance_red_missing_hand_morphs(self):
        # Intentional RED acceptance proof: frozen baseline cannot supply fists.
        for role in ("player","foe"):
            d,_ = read_glb(BASE/(role+"-rigged.glb"))
            self.assertEqual(d["meshes"][0].get("extras",{}).get("targetNames",[]),SHAPES)

    def test_fixture_nonidentity_frame_and_reordered_joints_preserve_original_basis(self):
        api = self.module("canonical_glb")
        with owned_fixture_dir() as tmp:
            tmp=Path(tmp); source=tmp/"source.glb"; raw=tmp/"raw.glb"
            expected=fixture(source); fixture(raw,raw=True)
            sockets=tmp/"sockets.json"; sockets.write_text(json.dumps({"version":1,"role":"player","space":"blender_world_z_up","front":{"open":[1,2,3],"half":[1,2,3],"closed":[1,2,3]},"rear":{"open":[1,2,3],"half":[1,2,3],"closed":[1,2,3]}}))
            out=tmp/"out.glb"; profile=tmp/"profile.json"
            report=api.canonicalize(source,raw,out,sockets,profile)
            sd,sb=read_glb(source); od,ob=read_glb(out)
            self.assertEqual(sd["nodes"],od["nodes"])
            self.assertEqual(sd["skins"][0]["joints"],od["skins"][0]["joints"])
            np.testing.assert_array_equal(api.GLB(source).accessor(sd["skins"][0]["inverseBindMatrices"]),api.GLB(out).accessor(od["skins"][0]["inverseBindMatrices"]))
            final=api.GLB(out); prim=od["meshes"][0]["primitives"][0]
            np.testing.assert_allclose(final.accessor(prim["attributes"]["POSITION"]),expected,atol=1e-6)
            self.assertEqual(set(final.accessor(prim["attributes"]["JOINTS_0"])[:,0]),{8})
            np.testing.assert_allclose(final.accessor(prim["targets"][0]["POSITION"]),[[.01,.02,0]]*3,atol=1e-7)
            p=json.loads(profile.read_text())
            # Blender (x,y,z) -> glTF (x,z,-y), forearm world head y=.15.
            np.testing.assert_allclose(p["hand_sockets"]["front"]["open"],[1,2.85,-2],atol=1e-7)
            self.assertEqual(report["skin_joints"],14)

    def test_bridge_refuses_baseline_overwrite_and_unknown_joint(self):
        api=self.module("canonical_glb")
        with owned_fixture_dir() as tmp:
            tmp=Path(tmp); src=tmp/"source.glb"; raw=tmp/"raw.glb"; fixture(src);fixture(raw,True)
            sockets=tmp/"sockets.json"; sockets.write_text("{}")
            with self.assertRaises(ValueError): api.canonicalize(src,raw,src,sockets,tmp/"profile.json")

    def test_checker_rejects_baseline_missing_hand_morphs(self):
        checker=self.module("check_retopology_assets")
        result=checker.check_asset(BASE/"player-rigged.glb",BASE/"player-rigged.glb")
        self.assertFalse(result["ok"])
        self.assertIn("required_morphs",[e["code"] for e in result["errors"]])

    def test_checker_detects_rig_drift_and_body_morph_leak(self):
        checker=self.module("check_retopology_assets")
        with owned_fixture_dir() as tmp:
            tmp=Path(tmp); src=tmp/"source.glb"; raw=tmp/"raw.glb"; fixture(src);fixture(raw,True,True)
            result=checker.check_asset(src,raw)
            codes=[e["code"] for e in result["errors"]]
            self.assertIn("canonical_nodes",codes)
            self.assertIn("joint_declaration",codes)
            self.assertIn("morph_hand_only",codes)

    def test_checker_rejects_truncated_png_atlas(self):
        checker=self.module("check_retopology_assets")
        with self.assertRaises(ValueError):checker.image_dimensions(png_atlas()[:33])

    def test_complete_fixture_passes_geometry_material_hand_acceptance(self):
        checker=self.module("check_retopology_assets")
        with owned_fixture_dir() as tmp:
            src,candidate=acceptance_pair(tmp);r=checker.check_asset(src,candidate)
            self.assertTrue(r["ok"],r["errors"])

    def test_checker_rejects_invalid_tangent_uv_and_pbr_texcoord(self):
        checker=self.module("check_retopology_assets");api=self.module("canonical_glb")
        with owned_fixture_dir() as tmp:
            src,candidate=acceptance_pair(tmp);b=api.Builder(api.GLB(candidate));a=b.doc["meshes"][0]["primitives"][0]["attributes"]
            a["TANGENT"]=b.accessor([[0,0,1,0]]*9,"VEC4")
            a["TEXCOORD_0"]=b.accessor([[0,0],[2,0],[0,1]]*3,"VEC2")
            b.doc["materials"][0]["normalTexture"]["texCoord"]=1;b.write(candidate)
            codes=[e["code"] for e in checker.check_asset(src,candidate)["errors"]]
            for code in ("tangent_basis","atlas_uv","pbr_texcoord"):self.assertIn(code,codes)

    def test_checker_rejects_forearm_weighted_morph_outside_source_hand_bounds(self):
        checker=self.module("check_retopology_assets");api=self.module("canonical_glb")
        with owned_fixture_dir() as tmp:
            src,candidate=acceptance_pair(tmp);g=api.GLB(candidate);b=api.Builder(g);p=b.doc["meshes"][0]["primitives"][0]
            pos=g.accessor(p["attributes"]["POSITION"]);pos[:3,0]+=2
            p["attributes"]["POSITION"]=b.accessor(pos,"VEC3",bounds=True);b.write(candidate)
            self.assertIn("morph_hand_only",[e["code"] for e in checker.check_asset(src,candidate)["errors"]])

    def test_checker_returns_errors_for_malformed_morph_accessor(self):
        checker=self.module("check_retopology_assets");api=self.module("canonical_glb")
        with owned_fixture_dir() as tmp:
            src,candidate=acceptance_pair(tmp);b=api.Builder(api.GLB(candidate));p=b.doc["meshes"][0]["primitives"][0]
            p["targets"][0]["NORMAL"]=b.accessor([[float("nan"),0,0]]*9,"VEC3");b.write(candidate)
            result=checker.check_asset(src,candidate)
            self.assertIn("morph_accessor",[e["code"] for e in result["errors"]])

    def test_bridge_rejects_raw_rest_bind_drift_before_writing_outputs(self):
        api=self.module("canonical_glb")
        with owned_fixture_dir() as tmp:
            tmp=Path(tmp);src=tmp/"source.glb";raw=tmp/"raw.glb";fixture(src);fixture(raw,True)
            g=api.GLB(raw);b=api.Builder(g);ibms=g.ibms().copy();ibms[:,:3,3]+=.1
            b.doc["skins"][0]["inverseBindMatrices"]=b.accessor(ibms.transpose(0,2,1).reshape(-1,16),"MAT4");b.write(raw)
            sockets=tmp/"sockets.json";sockets.write_text(json.dumps({"version":1,"role":"player","space":"blender_world_z_up",**{side:{state:[1,2,3] for state in ("open","half","closed")} for side in ("front","rear")}}))
            with self.assertRaisesRegex(ValueError,"rest.bind"):
                api.canonicalize(src,raw,tmp/"out.glb",sockets,tmp/"profile.json")
            self.assertFalse((tmp/"out.glb").exists())

    def test_bridge_transforms_morph_tangent_as_normalized_direction_delta(self):
        api=self.module("canonical_glb")
        with owned_fixture_dir() as tmp:
            tmp=Path(tmp);src=tmp/"source.glb";raw=tmp/"raw.glb";fixture(src);fixture(raw,True)
            b=api.Builder(api.GLB(raw));p=b.doc["meshes"][0]["primitives"][0]
            p["attributes"]["TANGENT"]=b.accessor([[1,0,0,1]]*3,"VEC4")
            p["targets"][0]["TANGENT"]=b.accessor([[0,.2,0]]*3,"VEC3");b.write(raw)
            sockets=tmp/"sockets.json";sockets.write_text(json.dumps({"version":1,"role":"player","space":"blender_world_z_up",**{side:{state:[1,2,3] for state in ("open","half","closed")} for side in ("front","rear")}}))
            api.canonicalize(src,raw,tmp/"out.glb",sockets,tmp/"profile.json")
            g=api.GLB(tmp/"out.glb");target=g.mesh_primitive()["targets"][0]
            np.testing.assert_allclose(g.accessor(target["TANGENT"]),[[-.0194193243,.1961161351,0]]*3,atol=1e-6)

    def test_checker_reports_malformed_skin_without_crashing(self):
        checker=self.module("check_retopology_assets");api=self.module("canonical_glb")
        with owned_fixture_dir() as tmp:
            src,candidate=acceptance_pair(tmp);b=api.Builder(api.GLB(candidate));b.doc["skins"][0]["inverseBindMatrices"]=999999;b.write(candidate)
            result=checker.check_asset(src,candidate)
            self.assertFalse(result["ok"]);self.assertIn("malformed_asset",[e["code"] for e in result["errors"]])

    def test_bridge_rejects_fractional_joint_indices_instead_of_truncating(self):
        api=self.module("canonical_glb")
        with owned_fixture_dir() as tmp:
            tmp=Path(tmp);src=tmp/"source.glb";raw=tmp/"raw.glb";fixture(src);fixture(raw,True)
            g=api.GLB(raw);b=api.Builder(g);p=b.doc["meshes"][0]["primitives"][0];joints=g.accessor(p["attributes"]["JOINTS_0"]).astype(float);joints[:,0]+=.25
            p["attributes"]["JOINTS_0"]=b.accessor(joints,"VEC4");b.write(raw)
            sockets=tmp/"sockets.json";sockets.write_text(json.dumps({"version":1,"role":"player","space":"blender_world_z_up",**{side:{state:[1,2,3] for state in ("open","half","closed")} for side in ("front","rear")}}))
            with self.assertRaisesRegex(ValueError,"JOINTS_0"):
                api.canonicalize(src,raw,tmp/"out.glb",sockets,tmp/"profile.json")

    def test_checker_rejects_float_joint_storage_and_negative_extra_weights(self):
        checker=self.module("check_retopology_assets");api=self.module("canonical_glb")
        with owned_fixture_dir() as tmp:
            src,candidate=acceptance_pair(tmp);g=api.GLB(candidate);b=api.Builder(g);a=b.doc["meshes"][0]["primitives"][0]["attributes"]
            a["JOINTS_0"]=b.accessor(g.accessor(a["JOINTS_0"]),"VEC4")
            a["WEIGHTS_1"]=b.accessor([[-.1,0,0,0]]*9,"VEC4");b.write(candidate)
            codes=[e["code"] for e in checker.check_asset(src,candidate)["errors"]]
            self.assertIn("joint_format",codes);self.assertIn("four_influences",codes)

    def test_hand_envelope_uses_original_forearm_geometry_not_upperarm_length(self):
        checker=self.module("check_retopology_assets");api=self.module("canonical_glb")
        with owned_fixture_dir() as tmp:
            src,candidate=acceptance_pair(tmp)
            for path in (src,candidate):
                b=api.Builder(api.GLB(path));b.doc["nodes"][7]["translation"]=[0,-1,0]
                b.doc["nodes"][8]["translation"]=[0,1.15,0];b.write(path)
            result=checker.check_asset(src,candidate)
            self.assertTrue(result["ok"],result["errors"])

    def test_bridge_cannot_overwrite_input_socket_json(self):
        api=self.module("canonical_glb")
        with owned_fixture_dir() as tmp:
            tmp=Path(tmp);src=tmp/"source.glb";raw=tmp/"raw.glb";fixture(src);fixture(raw,True)
            sockets=tmp/"sockets.json";sockets.write_text(json.dumps({"version":1,"role":"player","space":"blender_world_z_up",**{side:{state:[1,2,3] for state in ("open","half","closed")} for side in ("front","rear")}}))
            before=sockets.read_bytes()
            with self.assertRaisesRegex(ValueError,"overwrite"):
                api.canonicalize(src,raw,sockets,sockets,tmp/"profile.json")
            self.assertEqual(sockets.read_bytes(),before)

    def test_f1_triangle_storage_is_validated_before_casting_in_bridge_and_checker(self):
        api=self.module("canonical_glb");checker=self.module("check_retopology_assets")
        cases=[("fractional",5126,"SCALAR",False,np.arange(9)+.25),
               ("vector",5123,"VEC3",False,np.arange(9).reshape(3,3)),
               ("normalized",5123,"SCALAR",True,np.arange(9)),
               ("signed",5122,"SCALAR",False,np.arange(9))]
        with owned_fixture_dir() as tmp:
            tmp=Path(tmp);src,candidate=acceptance_pair(tmp);base=api.GLB(candidate)
            sockets=tmp/"sockets.json";sockets.write_text(json.dumps({"version":1,"role":"player","space":"blender_world_z_up",**{side:{state:[1,2,3] for state in ("open","half","closed")} for side in ("front","rear")}}))
            for label,component,kind,norm,data in cases:
                b=api.Builder(base);p=b.doc["meshes"][0]["primitives"][0]
                p["indices"]=b.accessor(data,kind,component);b.doc["accessors"][p["indices"]]["normalized"]=norm;b.write(candidate)
                with self.subTest(case=label,consumer="checker"):
                    result=checker.check_asset(src,candidate)
                    self.assertIn("triangle_indices",[e["code"] for e in result["errors"]])
                with self.subTest(case=label,consumer="bridge"):
                    with self.assertRaisesRegex(ValueError,"triangle"):
                        api.canonicalize(src,candidate,tmp/(label+".glb"),sockets,tmp/(label+".json"))

    def test_f1_unsigned_scalar_triangle_indices_remain_accepted(self):
        api=self.module("canonical_glb");checker=self.module("check_retopology_assets")
        with owned_fixture_dir() as tmp:
            src,candidate=acceptance_pair(tmp);base=api.GLB(candidate)
            for component in (5121,5123,5125):
                b=api.Builder(base);p=b.doc["meshes"][0]["primitives"][0];p["indices"]=b.accessor(np.arange(9),"SCALAR",component);b.write(candidate)
                self.assertTrue(checker.check_asset(src,candidate)["ok"])

    def test_f1_malformed_source_triangle_storage_is_not_trusted(self):
        api=self.module("canonical_glb");checker=self.module("check_retopology_assets")
        with owned_fixture_dir() as tmp:
            tmp=Path(tmp);src,candidate=acceptance_pair(tmp);b=api.Builder(api.GLB(src));p=b.doc["meshes"][0]["primitives"][0]
            p["indices"]=b.accessor(np.arange(9)+.25,"SCALAR");b.write(src)
            self.assertFalse(checker.check_asset(src,candidate)["ok"])
            sockets=tmp/"sockets.json";sockets.write_text(json.dumps({"version":1,"role":"player","space":"blender_world_z_up",**{side:{state:[1,2,3] for state in ("open","half","closed")} for side in ("front","rear")}}))
            with self.assertRaisesRegex(ValueError,"triangle"):
                api.canonicalize(src,candidate,tmp/"out.glb",sockets,tmp/"profile.json")

    def test_f2_base_accessor_view_offsets_counts_and_strides_are_bounded(self):
        api=self.module("canonical_glb");checker=self.module("check_retopology_assets")
        with owned_fixture_dir() as tmp:
            src,candidate=acceptance_pair(tmp);base=api.GLB(candidate)
            cases=[("short_view","view","byteLength",4), ("negative_view_offset","view","byteOffset",-4),
                   ("fractional_view_offset","view","byteOffset",.5), ("backing_buffer_crossing","view","byteOffset",len(base.buffers[0])-4),
                   ("negative_buffer","view","buffer",-1), ("negative_accessor_offset","accessor","byteOffset",-4),
                   ("fractional_accessor_offset","accessor","byteOffset",.5), ("unaligned_accessor_offset","accessor","byteOffset",2),
                   ("negative_count","accessor","count",-1), ("fractional_count","accessor","count",8.5),
                   ("short_stride","view","byteStride",8), ("unaligned_stride","view","byteStride",13),
                   ("zero_stride","view","byteStride",0)]
            for label,section,key,value in cases:
                b=api.Builder(base);idx=b.doc["meshes"][0]["primitives"][0]["attributes"]["POSITION"]
                a=b.doc["accessors"][idx];v=b.doc["bufferViews"][a["bufferView"]]
                (a if section=="accessor" else v)[key]=value;b.write(candidate)
                with self.subTest(case=label,consumer="reader"):
                    with self.assertRaises(ValueError):api.GLB(candidate).accessor(idx)
                with self.subTest(case=label,consumer="checker"):
                    self.assertFalse(checker.check_asset(src,candidate)["ok"])

    def test_f2_sparse_bounds_offsets_unsigned_order_and_range_are_validated(self):
        api=self.module("canonical_glb")
        with owned_fixture_dir() as tmp:
            src,candidate=acceptance_pair(tmp);b=api.Builder(api.GLB(candidate));idx=b.doc["meshes"][0]["primitives"][0]["attributes"]["POSITION"]
            a=b.doc["accessors"][idx];a.pop("bufferView")
            a["sparse"]={"count":2,"indices":{"bufferView":b.view(b"\0\1"),"componentType":5121},
                         "values":{"bufferView":b.view(struct.pack("<6f",0,.4,0,.05,.4,0))}}
            b.write(candidate);base=api.GLB(candidate)
            mutations=[("negative_index_offset","indices_offset",-1), ("fractional_value_offset","values_offset",.5),
                       ("negative_sparse_count","count",-1), ("too_many_sparse","count",10),
                       ("signed_sparse_indices","index_component",5120), ("short_index_view","index_length",1),
                       ("short_value_view","value_length",4), ("strided_sparse","index_stride",4),
                       ("negative_sparse_index","indices",b"\xff\0"), ("out_of_range_sparse","indices",b"\0\x09"),
                       ("duplicate_sparse","indices",b"\1\1"), ("unordered_sparse","indices",b"\1\0")]
            for label,kind,value in mutations:
                m=api.Builder(base);s=m.doc["accessors"][idx]["sparse"]
                if kind=="indices_offset":s["indices"]["byteOffset"]=value
                elif kind=="values_offset":s["values"]["byteOffset"]=value
                elif kind=="count":s["count"]=value
                elif kind=="index_component":s["indices"]["componentType"]=value
                elif kind=="index_length":m.doc["bufferViews"][s["indices"]["bufferView"]]["byteLength"]=value
                elif kind=="value_length":m.doc["bufferViews"][s["values"]["bufferView"]]["byteLength"]=value
                elif kind=="index_stride":m.doc["bufferViews"][s["indices"]["bufferView"]]["byteStride"]=value
                else:s["indices"]["bufferView"]=m.view(value)
                m.write(candidate)
                with self.subTest(case=label):
                    with self.assertRaises(ValueError):api.GLB(candidate).accessor(idx)

    def test_f2_valid_interleaved_sparse_and_padded_matrix_accessors(self):
        api=self.module("canonical_glb")
        with owned_fixture_dir() as tmp:
            src,candidate=acceptance_pair(tmp);b=api.Builder(api.GLB(candidate))
            inter=b.accessor([[1,2,3,99],[4,5,6,99]],"VEC4");entry=b.doc["accessors"][inter];entry["type"]="VEC3"
            b.doc["bufferViews"][entry["bufferView"]]["byteStride"]=16
            matrix=b.accessor([[1,2,3,0,4,5,6,0,7,8,9,0]],"MAT3",5121)
            sparse=b.accessor([[0,0,0]]*3,"VEC3");s=b.doc["accessors"][sparse];s.pop("bufferView")
            s["sparse"]={"count":1,"indices":{"bufferView":b.view(b"\x01"),"componentType":5121},"values":{"bufferView":b.view(struct.pack("<3f",7,8,9))}}
            b.write(candidate);g=api.GLB(candidate)
            np.testing.assert_array_equal(g.accessor(inter),[[1,2,3],[4,5,6]])
            np.testing.assert_array_equal(g.accessor(matrix),[[1,2,3,4,5,6,7,8,9]])
            np.testing.assert_array_equal(g.accessor(sparse),[[0,0,0],[7,8,9],[0,0,0]])

    def test_f3_png_requires_supported_colour_and_legal_chunk_structure(self):
        checker=self.module("check_retopology_assets");api=self.module("canonical_glb")
        def chunk(kind,payload):return struct.pack(">I",len(payload))+kind+payload+struct.pack(">I",zlib.crc32(kind+payload))
        rgb=png_atlas();head=rgb[:33];tail=rgb[33:];rgba=png_atlas(6)
        compressed=zlib.compress((b"\0"+b"\0"*(4096*3))*4096);middle=len(compressed)//2
        cases={"indexed_without_palette":png_atlas(3),
               "unknown_critical":head+chunk(b"ABCD",b"test")+tail,
               "noncontiguous_idat":head+chunk(b"IDAT",compressed[:middle])+chunk(b"tEXt",b"x\0y")+chunk(b"IDAT",compressed[middle:])+chunk(b"IEND",b""),
               "late_palette":rgb[:-12]+chunk(b"PLTE",b"\0\0\0")+rgb[-12:],
               "invalid_palette_length":head+chunk(b"PLTE",b"\0")+tail,
               "rgba_transparency":rgba[:33]+chunk(b"tRNS",b"\0"*6)+rgba[33:]}
        for label,data in cases.items():
            with self.subTest(case=label):
                with self.assertRaises(ValueError):checker.image_dimensions(data)
        with owned_fixture_dir() as tmp:
            src,candidate=acceptance_pair(tmp);b=api.Builder(api.GLB(candidate));b.doc["images"][0]={"bufferView":b.view(cases["indexed_without_palette"]),"mimeType":"image/png"};b.write(candidate)
            self.assertIn("pbr_image",[e["code"] for e in checker.check_asset(src,candidate)["errors"]])

    def test_f3_rgb_rgba_8_and_16_bit_atlases_remain_decodable(self):
        checker=self.module("check_retopology_assets")
        for colour,depth in ((2,8),(6,8),(2,16),(6,16)):
            with self.subTest(colour=colour,depth=depth):self.assertEqual(checker.image_dimensions(png_atlas(colour,depth)),[4096,4096])

    def test_f4_unique_staging_preserves_source_named_as_legacy_temporary_file(self):
        api=self.module("canonical_glb")
        with owned_fixture_dir() as tmp:
            tmp=Path(tmp);src=tmp/"out.glb.tmp";raw=tmp/"raw.glb";fixture(src);fixture(raw,True)
            sockets=tmp/"sockets.json";sockets.write_text(json.dumps({"version":1,"role":"player","space":"blender_world_z_up",**{side:{state:[1,2,3] for state in ("open","half","closed")} for side in ("front","rear")}}))
            before=src.read_bytes();api.canonicalize(src,raw,tmp/"out.glb",sockets,tmp/"profile.json")
            self.assertEqual(src.read_bytes(),before)
            self.assertFalse(list(tmp.glob(".out.glb.*.tmp")))

    def test_f4_external_buffers_and_images_are_protected_from_both_outputs(self):
        api=self.module("canonical_glb")
        for owner in ("raw","source"):
            for resource in ("image","buffer"):
                for destination in ("glb","profile"):
                    with self.subTest(owner=owner,resource=resource,destination=destination),owned_fixture_dir() as tmp:
                        tmp=Path(tmp);src=tmp/"source.glb";raw=tmp/"raw.glb";fixture(src);fixture(raw,True)
                        external=tmp/(owner+"-external.bin");selected=raw if owner=="raw" else src
                        doc,payload=read_glb(selected)
                        if resource=="image":
                            external.write_bytes(b"original image dependency");doc["images"]=[{"uri":external.name.replace(" ","%20")}]
                        else:
                            external.write_bytes(payload[:doc["buffers"][0]["byteLength"]]);doc["buffers"][0]["uri"]=external.name.replace(" ","%20")
                        encoded=json.dumps(doc,separators=(",",":")).encode();encoded+=b" "*((-len(encoded))%4)
                        if resource=="buffer":selected.write_bytes(struct.pack("<III",0x46546c67,2,20+len(encoded))+struct.pack("<II",len(encoded),0x4e4f534a)+encoded)
                        else:selected.write_bytes(struct.pack("<III",0x46546c67,2,28+len(encoded)+len(payload))+struct.pack("<II",len(encoded),0x4e4f534a)+encoded+struct.pack("<II",len(payload),0x004e4942)+payload)
                        sockets=tmp/"sockets.json";sockets.write_text(json.dumps({"version":1,"role":"player","space":"blender_world_z_up",**{side:{state:[1,2,3] for state in ("open","half","closed")} for side in ("front","rear")}}))
                        before={p:p.read_bytes() for p in (src,raw,sockets,external)}
                        output=external if destination=="glb" else tmp/"out.glb";profile=external if destination=="profile" else tmp/"profile.json"
                        with self.assertRaisesRegex(ValueError,"overwrite"):
                            api.canonicalize(src,raw,output,sockets,profile)
                        for path,data in before.items():self.assertEqual(path.read_bytes(),data)

    def test_f4_cli_report_collision_is_rejected_before_any_output_write(self):
        for target in ("source","raw","sockets","output","profile"):
            with self.subTest(target=target),owned_fixture_dir() as tmp:
                tmp=Path(tmp);paths={name:tmp/(name+suffix) for name,suffix in (("source",".glb"),("raw",".glb"),("sockets",".json"),("output",".glb"),("profile",".json"))}
                fixture(paths["source"]);fixture(paths["raw"],True)
                paths["sockets"].write_text(json.dumps({"version":1,"role":"player","space":"blender_world_z_up",**{side:{state:[1,2,3] for state in ("open","half","closed")} for side in ("front","rear")}}))
                before={p:p.read_bytes() for p in (paths["source"],paths["raw"],paths["sockets"])}
                process=subprocess.run([sys.executable,str(HERE/"canonical_glb.py"),*[str(paths[k]) for k in ("source","raw","output","sockets","profile")],"--report",str(paths[target])],capture_output=True,text=True)
                self.assertNotEqual(process.returncode,0)
                for p,data in before.items():self.assertEqual(p.read_bytes(),data)
                self.assertFalse(paths["output"].exists());self.assertFalse(paths["profile"].exists())

    def test_f4_report_writes_protect_external_dependencies_and_checker_inputs(self):
        api=self.module("canonical_glb")
        with owned_fixture_dir() as tmp:
            tmp=Path(tmp);src=tmp/"source.glb";raw=tmp/"raw.glb";fixture(src);fixture(raw,True)
            external=tmp/"image.png";external.write_bytes(png_atlas())
            b=api.Builder(api.GLB(raw));b.doc["images"]=[{"uri":external.name}];b.write(raw)
            sockets=tmp/"sockets.json";sockets.write_text(json.dumps({"version":1,"role":"player","space":"blender_world_z_up",**{side:{state:[1,2,3] for state in ("open","half","closed")} for side in ("front","rear")}}))
            before={p:p.read_bytes() for p in (src,raw,external,sockets)}
            with self.subTest(consumer="bridge_report"):
                process=subprocess.run([sys.executable,str(HERE/"canonical_glb.py"),str(src),str(raw),str(tmp/"out.glb"),str(sockets),str(tmp/"profile.json"),"--report",str(external)],capture_output=True,text=True)
                self.assertNotEqual(process.returncode,0)
                for p,data in before.items():self.assertEqual(p.read_bytes(),data)
                self.assertFalse((tmp/"out.glb").exists())
        for target in ("source","candidate","profile"):
            with self.subTest(consumer="checker_report",target=target),owned_fixture_dir() as tmp:
                tmp=Path(tmp);src,candidate=acceptance_pair(tmp);profile=tmp/"profile.json";profile.write_text("{}")
                paths={"source":src,"candidate":candidate,"profile":profile};before={p:p.read_bytes() for p in paths.values()}
                process=subprocess.run([sys.executable,str(HERE/"check_retopology_assets.py"),str(src),str(candidate),"--profile",str(profile),"--report",str(paths[target])],capture_output=True,text=True)
                for p,data in before.items():self.assertEqual(p.read_bytes(),data)

    def test_f4_percent_encoded_external_image_resolves_without_mutation(self):
        api=self.module("canonical_glb")
        with owned_fixture_dir() as tmp:
            tmp=Path(tmp);src=tmp/"source.glb";raw=tmp/"raw.glb";fixture(src);fixture(raw,True)
            image=tmp/"image space.png";pixels=png_atlas();image.write_bytes(pixels)
            b=api.Builder(api.GLB(raw));b.doc["images"]=[{"uri":"image%20space.png"}];b.write(raw)
            sockets=tmp/"sockets.json";sockets.write_text(json.dumps({"version":1,"role":"player","space":"blender_world_z_up",**{side:{state:[1,2,3] for state in ("open","half","closed")} for side in ("front","rear")}}))
            api.canonicalize(src,raw,tmp/"out.glb",sockets,tmp/"profile.json")
            output=api.GLB(tmp/"out.glb");self.assertEqual(output.view(output.doc["images"][0]["bufferView"]),pixels)
            self.assertEqual(image.read_bytes(),pixels)

    def test_f4_report_does_not_drop_dependencies_when_another_uri_is_unsupported(self):
        api=self.module("canonical_glb")
        with owned_fixture_dir() as tmp:
            tmp=Path(tmp);src,candidate=acceptance_pair(tmp);dependency=tmp/"dependency.png";data=png_atlas();dependency.write_bytes(data)
            b=api.Builder(api.GLB(candidate));b.doc["images"][0]={"uri":dependency.name};b.doc["images"].append({"uri":"https://invalid.example/image.png"});b.write(candidate)
            process=subprocess.run([sys.executable,str(HERE/"check_retopology_assets.py"),str(src),str(candidate),"--report",str(dependency)],capture_output=True,text=True)
            self.assertNotEqual(process.returncode,0);self.assertEqual(dependency.read_bytes(),data)


if __name__ == "__main__": unittest.main(verbosity=2)
