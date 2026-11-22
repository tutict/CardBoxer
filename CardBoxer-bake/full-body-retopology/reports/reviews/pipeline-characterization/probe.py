"""Focused independent review probes; no baseline/author/project mutations."""
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from canonical_glb import GLB, Builder, canonicalize, sha256
from check_retopology_assets import check_asset, image_dimensions
from pipeline_test import acceptance_pair, fixture

manifest = json.loads((ROOT / "reports/reviews/pipeline-initial.patch.manifest.json").read_text(encoding="utf-8"))
boundary = [{"path": e["path"], "matches": sha256(Path(e["path"])) == e["sha256"]} for e in manifest]
results = {"hash_boundary": boundary, "probes": []}
source, candidate = acceptance_pair(HERE)
base = GLB(candidate)
control = check_asset(source, candidate)
results["control"] = {"ok": control["ok"], "errors": control["errors"]}

def probe(name, mutate):
    b = Builder(base)
    mutate(b)
    path = HERE / (name + ".glb")
    b.write(path)
    r = check_asset(source, path)
    results["probes"].append({"name": name, "ok": r["ok"], "errors": r["errors"], "metrics": r["metrics"]})

def fractional_indices(b):
    p = b.doc["meshes"][0]["primitives"][0]
    p["indices"] = b.accessor(np.arange(9) + .25, "SCALAR")
probe("fractional_float_triangle_indices", fractional_indices)

def vector_indices(b):
    p = b.doc["meshes"][0]["primitives"][0]
    p["indices"] = b.accessor(np.arange(9).reshape(3, 3), "VEC3", 5123)
probe("vec3_triangle_indices", vector_indices)

def short_view(b):
    p = b.doc["meshes"][0]["primitives"][0]
    acc = b.doc["accessors"][p["attributes"]["POSITION"]]
    b.doc["bufferViews"][acc["bufferView"]]["byteLength"] = 4
probe("position_accessor_crosses_view_boundary", short_view)

def png_chunk(kind, payload):
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))
indexed_png = (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 4096, 4096, 8, 3, 0, 0, 0))
               + png_chunk(b"IDAT", zlib.compress((b"\0" + b"\0" * 4096) * 4096)) + png_chunk(b"IEND", b""))
def missing_palette(b):
    b.doc["images"][0] = {"bufferView": b.view(indexed_png), "mimeType": "image/png"}
probe("indexed_png_missing_required_palette", missing_palette)

sockets = HERE / "sockets.json"
sockets.write_text(json.dumps({"version": 1, "role": "player", "space": "blender_world_z_up",
                              **{side: {state: [1, 2, 3] for state in ("open", "half", "closed")} for side in ("front", "rear")}}))
raw = HERE / "raw.glb"
fixture(raw, raw=True)
collision_source = HERE / "collision-output.glb.tmp"
fixture(collision_source)
before = sha256(collision_source)
try:
    canonicalize(collision_source, raw, HERE / "collision-output.glb", sockets, HERE / "collision-profile.json")
    exc = None
except Exception as caught:
    exc = type(caught).__name__ + ": " + str(caught)
results["probes"].append({"name": "source_is_output_temporary_path", "exception": exc,
                          "source_existed_before": True, "source_exists_after": collision_source.exists(),
                          "source_sha256_before": before, "output_exists": (HERE / "collision-output.glb").exists()})

external_image = HERE / "external-input.png"
external_image.write_bytes(indexed_png)
before = sha256(external_image)
b = Builder(GLB(raw))
b.doc["images"] = [{"uri": external_image.name}]
external_raw = HERE / "raw-external.glb"
b.write(external_raw)
try:
    canonicalize(source, external_raw, external_image, sockets, HERE / "external-profile.json")
    exc = None
except Exception as caught:
    exc = type(caught).__name__ + ": " + str(caught)
results["probes"].append({"name": "output_overwrites_raw_external_image", "exception": exc,
                          "image_sha256_before": before, "image_sha256_after": sha256(external_image),
                          "image_magic_after": external_image.read_bytes()[:4].decode("ascii")})

provenance = json.loads((ROOT / "tools/pipeline_roundtrip/blender-roundtrip-provenance.json").read_text(encoding="utf-8"))
results["roundtrip_hashes"] = []
for record in provenance:
    r = json.loads((ROOT / "tools/pipeline_roundtrip" / (record["role"] + "-roundtrip-report.json")).read_text(encoding="utf-8"))
    results["roundtrip_hashes"].append({"role": record["role"], "source_matches_provenance": sha256(Path(record["source"])) == record["source_sha256"],
        "raw_matches_provenance": sha256(Path(record["raw"])) == record["raw_sha256"],
        "canonical_matches_report": sha256(Path(r["output"])) == r["output_sha256"],
        "bridge_matches_report": sha256(ROOT / "tools/canonical_glb.py") == r["pipeline_sha256"]})
(HERE / "results.json").write_text(json.dumps(results, indent=2) + "\n")
print(json.dumps(results, indent=2))
