"""Executable compatibility tests; run with Blender's bundled Python (NumPy)."""
from __future__ import annotations
import copy
import importlib.util
import json
import struct
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


def png_atlas():
    def chunk(kind, payload):
        return struct.pack(">I",len(payload))+kind+payload+struct.pack(">I",zlib.crc32(kind+payload))
    # Real decodable 4K RGB PNG, not an IHDR-only dimension stub.
    pixels=(b"\0"+b"\x80\x80\xff"*4096)*4096
    return b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",4096,4096,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(pixels))+chunk(b"IEND",b"")


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


if __name__ == "__main__": unittest.main(verbosity=2)
