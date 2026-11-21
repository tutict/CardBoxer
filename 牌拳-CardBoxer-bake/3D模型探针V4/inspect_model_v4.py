"""Structural inspection of the V2 artifacts, keyed by FILE SIGNATURE not index.

V1's inspector hard-coded artifact_01.zip / artifact_02.png / ... but the service
returns URLs in a different order between jobs (V2: png=01, zip=02, glb=03,
fbx=04). Reading by number silently inspects the wrong file. Here every
artifact_* is classified from its magic bytes, then the GLB index buffer is
walked with union-find to count disconnected shells (the bone-heat blocker).
"""
from __future__ import annotations

import json
import struct
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_JSON = HERE / "model_inspection.json"
OUT_LOG = HERE / "inspect_model.log"


def classify(path: Path) -> str:
    head = path.read_bytes()[:64]
    if head[:4] == b"glTF":
        return "glb"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:2] == b"PK":
        return "zip"
    if b"Kaydara FBX Binary" in head:
        return "fbx"
    return "obj" if head[:2] in (b"v ", b"# ", b"o ") else "unknown"


files = {}
for p in sorted(HERE.glob("artifact_*")):
    if p.is_file():
        files.setdefault(classify(p), []).append(p)
assert "glb" in files, "no GLB found by magic bytes"
GLB = files["glb"][0]
ZIPF = files.get("zip", [None])[0]
FBX = files.get("fbx", [None])[0]


def glb_json(path: Path):
    data = path.read_bytes()
    version, total = struct.unpack("<II", data[4:12])
    off, js, blob, bin_size = 12, None, b"", 0
    while off + 8 <= len(data):
        (length,) = struct.unpack("<I", data[off:off + 4])
        ctype = data[off + 4:off + 8]
        payload = data[off + 8:off + 8 + length]
        if ctype == b"JSON":
            js = json.loads(payload.decode("utf-8"))
        elif ctype == b"BIN\x00":
            blob, bin_size = payload, len(payload)
        off += 8 + length
    return js, blob, {"gltf_version": version, "declared_length": total,
                      "file_bytes": len(data), "bin_chunk_bytes": bin_size}


g, blob, meta = glb_json(GLB)
counts = {k: len(g.get(k, [])) for k in (
    "scenes", "nodes", "meshes", "materials", "textures", "images",
    "skins", "animations", "accessors", "bufferViews", "buffers", "samplers",
    "cameras",
)}
counts["extensionsUsed"] = g.get("extensionsUsed", [])

vertices = triangles = primitives = 0
mesh_names = []
pos_accessor = idx_accessor = None
for m in g.get("meshes", []):
    mesh_names.append(m.get("name", ""))
    for p in m.get("primitives", []):
        primitives += 1
        pos = p.get("attributes", {}).get("POSITION")
        idx = p.get("indices")
        if pos is not None:
            vertices += g["accessors"][pos].get("count", 0)
            pos_accessor = pos
        if idx is not None:
            triangles += g["accessors"][idx].get("count", 0) // 3
            idx_accessor = idx
        elif pos is not None:
            triangles += g["accessors"][pos].get("count", 0) // 3

COMPONENT = {5121: ("B", 1), 5123: ("H", 2), 5125: ("I", 4)}


def read_scalars(idx):
    acc = g["accessors"][idx]
    fmt, width = COMPONENT[acc["componentType"]]
    bv = g["bufferViews"][acc["bufferView"]]
    base = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = bv.get("byteStride") or width
    return [struct.unpack("<" + fmt, blob[base + i * stride:
                                         base + i * stride + width])[0]
            for i in range(acc["count"])]


shells = None
shell_sizes = []
if idx_accessor is not None and pos_accessor is not None:
    nv = g["accessors"][pos_accessor]["count"]
    indices = read_scalars(idx_accessor)
    parent, size = list(range(nv)), [1] * nv

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

    for i in range(0, len(indices) - 2, 3):
        a, b, c = indices[i], indices[i + 1], indices[i + 2]
        union(a, b)
        union(b, c)
    roots = {}
    for v in range(nv):
        r = find(v)
        roots[r] = roots.get(r, 0) + 1
    shell_sizes = sorted(roots.values(), reverse=True)
    shells = len(shell_sizes)

texture_refs = []
for mat in g.get("materials", []):
    for key, val in mat.get("pbrMetallicRoughness", {}).items():
        if "Texture" in key and isinstance(val, dict):
            texture_refs.append(key)
    for key in ("normalTexture", "occlusionTexture", "emissiveTexture"):
        if key in mat:
            texture_refs.append(key)

images = [{"name": im.get("name"), "mimeType": im.get("mimeType"),
           "embedded": "bufferView" in im} for im in g.get("images", [])]
node_names = [n.get("name", "") for n in g.get("nodes", [])]
rig_like = [n for n in node_names if any(
    t in n.lower() for t in ("bone", "joint", "spine", "hip", "head", "skel", "root"))]

zip_entries = []
if ZIPF:
    with zipfile.ZipFile(ZIPF) as z:
        zip_entries = [{"name": i.filename, "size": i.file_size}
                       for i in z.infolist()]
        z.extractall(HERE / "obj_bundle")

fbx_tokens = {}
if FBX:
    fb = FBX.read_bytes()
    fbx_tokens = {t.decode(): fb.count(t) for t in (
        b"LimbNode", b"Deformer", b"Skin", b"Skeleton", b"BindPose",
        b"Geometry", b"Material", b"Texture", b"Animation")}

report = {
    "artifacts_by_signature": {k: [p.name for p in v] for k, v in files.items()},
    "glb": meta,
    "counts": counts,
    "vertices_total": vertices,
    "triangles_total": triangles,
    "primitives_total": primitives,
    "mesh_names": mesh_names,
    "material_texture_refs": texture_refs,
    "images": images,
    "has_skin": counts["skins"] > 0,
    "has_animation": counts["animations"] > 0,
    "node_names_sample": node_names[:30],
    "rig_like_node_names": rig_like[:30],
    "connected_shells_unionfind": shells,
    "shell_sizes_top10": shell_sizes[:10],
    "zip_entries": zip_entries,
    "zip_entry_count": len(zip_entries),
    "fbx_bytes": FBX.stat().st_size if FBX else 0,
    "fbx_token_counts": fbx_tokens,
}
OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

lines = [
    "SIGNATURES " + json.dumps(report["artifacts_by_signature"], ensure_ascii=False),
    "GLB " + json.dumps(meta),
    "COUNTS " + json.dumps({k: v for k, v in counts.items()
                            if k != "extensionsUsed"}),
    f"GEOMETRY vertices={vertices} triangles={triangles} "
    f"primitives={primitives} meshes={len(mesh_names)}",
    f"MATERIALS texture_refs={len(texture_refs)} images={len(images)}",
    f"RIG has_skin={report['has_skin']} has_animation={report['has_animation']} "
    f"rig_like_nodes={len(rig_like)}",
    f"SHELLS unionfind={shells} top10={shell_sizes[:10]}",
    f"ZIP entries={len(zip_entries)}",
] + [f"  {e['name']} {e['size']} B" for e in zip_entries[:12]] + [
    "FBX_TOKENS " + json.dumps(fbx_tokens),
    "INSPECT_V2_OK",
]
OUT_LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines), flush=True)
