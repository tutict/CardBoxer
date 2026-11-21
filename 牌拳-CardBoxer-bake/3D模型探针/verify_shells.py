"""Independent cross-check of the '861 disconnected shells' claim.

probe_rigfit2.py used bmesh on the imported Blender mesh. This script does NOT
use Blender: it parses the GLB index buffer directly and runs union-find over
triangle vertex indices. Two independent implementations agreeing is the point.
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
GLB = HERE / "artifact_03.glb"
RIGFIT2 = HERE / "rigfit2_result.json"
OUT = HERE / "verify_shells.log"

data = GLB.read_bytes()
assert data[:4] == b"glTF", "not a GLB"
version, total = struct.unpack("<II", data[4:12])
off, js, blob = 12, None, b""
while off + 8 <= len(data):
    (length,) = struct.unpack("<I", data[off:off + 4])
    ctype = data[off + 4:off + 8]
    payload = data[off + 8:off + 8 + length]
    if ctype == b"JSON":
        js = json.loads(payload.decode("utf-8"))
    elif ctype == b"BIN\x00":
        blob = payload
    off += 8 + length

COMPONENT = {5121: ("B", 1), 5123: ("H", 2), 5125: ("I", 4)}


def read_accessor(idx):
    acc = js["accessors"][idx]
    fmt, width = COMPONENT[acc["componentType"]]
    ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3}[acc["type"]]
    bv = js["bufferViews"][acc["bufferView"]]
    base = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = bv.get("byteStride") or (width * ncomp)
    count = acc["count"]
    out = []
    for i in range(count):
        raw = blob[base + i * stride: base + i * stride + width * ncomp]
        out.append(struct.unpack("<" + fmt * ncomp, raw))
    return out


prim = js["meshes"][0]["primitives"][0]
pos_idx = prim["attributes"]["POSITION"]
idx_idx = prim["indices"]
nv = js["accessors"][pos_idx]["count"]
indices = [t[0] for t in read_accessor(idx_idx)]
assert len(indices) % 3 == 0
assert max(indices) < nv

parent = list(range(nv))
size = [1] * nv


def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def union(a, b):
    ra, rb = find(a), find(b)
    if ra == rb:
        return
    if size[ra] < size[rb]:
        ra, rb = rb, ra
    parent[rb] = ra
    size[ra] += size[rb]


for i in range(0, len(indices), 3):
    a, b, c = indices[i], indices[i + 1], indices[i + 2]
    union(a, b)
    union(b, c)

roots = {}
for v in range(nv):
    r = find(v)
    roots[r] = roots.get(r, 0) + 1
sizes = sorted(roots.values(), reverse=True)

report = {
    "glb_sha256": hashlib.sha256(data).hexdigest(),
    "gltf_version": version,
    "declared_length": total,
    "file_bytes": len(data),
    "vertices": nv,
    "indices": len(indices),
    "triangles": len(indices) // 3,
    "connected_shells_unionfind": len(sizes),
    "shell_sizes_top10": sizes[:10],
    "bmesh_connected_components": None,
    "bmesh_sizes_top10": None,
    "verdict": None,
}

if RIGFIT2.exists():
    other = json.loads(RIGFIT2.read_text(encoding="utf-8"))["topology"]
    report["bmesh_connected_components"] = other["connected_components"]
    report["bmesh_sizes_top10"] = other["component_sizes_top10"]
    same_count = report["connected_shells_unionfind"] == other["connected_components"]
    same_sizes = report["shell_sizes_top10"] == other["component_sizes_top10"]
    report["verdict"] = (
        "SHELLS_CROSSCHECK_OK" if same_count and same_sizes else
        f"SHELLS_MISMATCH count={same_count} sizes={same_sizes}"
    )

lines = [f"GLB sha256={report['glb_sha256']}",
         f"vertices={nv} indices={len(indices)} triangles={len(indices)//3}",
         f"UNIONFIND shells={len(sizes)} top10={sizes[:10]}",
         f"BMESH    components={report['bmesh_connected_components']} "
         f"top10={report['bmesh_sizes_top10']}",
         report["verdict"]]
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
(HERE / "verify_shells.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print("\n".join(lines), flush=True)
