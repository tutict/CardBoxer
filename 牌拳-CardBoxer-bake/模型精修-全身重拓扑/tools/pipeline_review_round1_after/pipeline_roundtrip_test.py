"""Real Blender roundtrip compatibility tests; first run pipeline_blender_roundtrip.py.

No authoring/project/baseline writes. Outputs and provenance stay in tools/.
Vertex comparisons use symmetric nearest distances to handle exporter seam ordering.
"""
import itertools
import json
import unittest
from pathlib import Path
import numpy as np
from canonical_glb import GLB,canonicalize,sha256,skin_rest_vertices,transform_points

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/"tools/pipeline_roundtrip"


def nearest_error(reference,points,tolerance=1e-5):
    """Spatial hash independent of exporter ordering; search neighboring cells."""
    cells={}
    for i,key in enumerate(np.floor(reference/tolerance).astype(np.int64)):
        cells.setdefault(tuple(key),[]).append(i)
    offsets=list(itertools.product((-1,0,1),repeat=3));worst=0.
    for point,key in zip(points,np.floor(points/tolerance).astype(np.int64)):
        candidates=[]
        for delta in offsets:candidates.extend(cells.get(tuple(key+delta),()))
        if not candidates:return float("inf")
        distance=float(np.linalg.norm(reference[candidates]-point,axis=1).min())
        worst=max(worst,distance)
    return worst


class RealRoundtripTests(unittest.TestCase):
    def verify_role(self,role):
        source=ROOT/"baseline/assets/3d"/(role+"-rigged.glb")
        raw=OUT/(role+"-roundtrip-raw.glb");output=OUT/(role+"-roundtrip-canonical.glb")
        before=sha256(source)
        self.assertTrue(raw.is_file(),"Run the owned Blender diagnostic before this test")
        socket=OUT/(role+"-diagnostic-sockets.json");profile=OUT/(role+"-diagnostic-profile.json")
        socket.write_text(json.dumps({"version":1,"role":role,"space":"blender_world_z_up",
                                     **{side:{state:[0,0,0] for state in ("open","half","closed")} for side in ("front","rear")}}),encoding="utf-8")
        report=canonicalize(source,raw,output,socket,profile)
        s=GLB(source);g=GLB(output);r=GLB(raw)
        self.assertEqual(g.doc["nodes"],s.doc["nodes"])
        self.assertEqual(g.joint_names(),s.joint_names());self.assertEqual(len(g.joint_names()),14)
        self.assertEqual({k:v for k,v in g.skin().items() if k!="inverseBindMatrices"},{k:v for k,v in s.skin().items() if k!="inverseBindMatrices"})
        np.testing.assert_array_equal(g.ibms(),s.ibms())
        source_pos=s.accessor(s.mesh_primitive()["attributes"]["POSITION"])
        canonical_pos=g.accessor(g.mesh_primitive()["attributes"]["POSITION"])
        canonical_to_source=nearest_error(source_pos,canonical_pos)
        source_to_canonical=nearest_error(canonical_pos,source_pos)
        self.assertLessEqual(canonical_to_source,1e-5);self.assertLessEqual(source_to_canonical,1e-5)
        world=transform_points(g.globals()[g.mesh_node()],canonical_pos)
        rest_error=float(np.linalg.norm(skin_rest_vertices(g)-world,axis=1).max())
        self.assertLessEqual(rest_error,1e-5);self.assertLessEqual(report["world_rest_transfer_error_m"],1e-5)
        self.assertEqual(before,sha256(source))
        report.update(canonical_to_source_max_m=canonical_to_source,source_to_canonical_max_m=source_to_canonical,
                      source_vertices=len(source_pos),raw_nodes_equal_source=r.doc["nodes"]==s.doc["nodes"],
                      raw_ibms_equal_source=bool(np.array_equal(r.ibms(),s.ibms())),
                      source_unchanged=True,diagnostic_sockets_only=True,
                      test_script_sha256=sha256(Path(__file__)))
        (OUT/(role+"-roundtrip-report.json")).write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        print("REAL_ROUNDTRIP_PASS",role,canonical_to_source,source_to_canonical,rest_error,flush=True)

    def test_player_unedited_roundtrip_original_rig_and_rest_geometry(self):self.verify_role("player")
    def test_foe_unedited_roundtrip_original_rig_and_rest_geometry(self):self.verify_role("foe")


if __name__=="__main__":unittest.main(verbosity=2)
