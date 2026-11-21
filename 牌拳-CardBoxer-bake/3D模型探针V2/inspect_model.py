"""Structural inspection of the generated 3D artifacts.

The point is NOT "does it look nice" (that is decided by eye) but:
    - is there a skeleton / skin / animation already in the file?
    - how many vertices/triangles, meshes and separate parts?
    - are PBR texture maps actually present?
    - what is inside the OBJ bundle, and does the FBX carry rig data?

Those four answers decide whether the 11-joint baked2 table can be retargeted
onto this character, and how much work that would be.
"""
from __future__ import annotations

import json
import struct
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
GLB = HERE / "artifact_03.glb"
ZIPF = HERE / "artifact_01.zip"
FBX = HERE / "artifact_04.fbx"


def glb_json(path: Path):
    data = path.read_bytes()
    assert data[:4] == b"glTF", "not a GLB"
    version, total = struct.unpack("<II", data[4:12])
    off, js, bin_size = 12, None, 0
    while off + 8 <= len(data):
        (length,) = struct.unpack("<I", data[off:off + 4])
        ctype = data[off + 4:off + 8]
        payload = data[off + 8:off + 8 + length]
        if ctype == b"JSON":
            js = json.loads(payload.decode("utf-8"))
        elif ctype == b"BIN\x00":
            bin_size = len(payload)
        off += 8 + length
    return js, {"gltf_version": version, "declared_length": total,
                "file_bytes": len(data), "bin_chunk_bytes": bin_size}


g, meta = glb_json(GLB)
counts = {k: len(g.get(k, [])) for k in (
    "scenes", "nodes", "meshes", "materials", "textures", "images",
    "skins", "animations", "accessors", "bufferViews", "buffers", "samplers",
    "cameras", "extensionsUsed",
)}
counts["extensionsUsed"] = g.get("extensionsUsed", [])

vertices = triangles = primitives = 0
mesh_names = []
for m in g.get("meshes", []):
    mesh_names.append(m.get("name", ""))
    for p in m.get("primitives", []):
        primitives += 1
        pos = p.get("attributes", {}).get("POSITION")
        if pos is not None:
            vertices += g["accessors"][pos].get("count", 0)
        idx = p.get("indices")
        if idx is not None:
            triangles += g["accessors"][idx].get("count", 0) // 3
        elif pos is not None:
            triangles += g["accessors"][pos].get("count", 0) // 3

texture_refs = []
for mat in g.get("materials", []):
    pbr = mat.get("pbrMetallicRoughness", {})
    for key, val in pbr.items():
        if "Texture" in key and isinstance(val, dict):
            texture_refs.append(key)
    for key in ("normalTexture", "occlusionTexture", "emissiveTexture"):
        if key in mat:
            texture_refs.append(key)

images = [{
    "name": im.get("name"),
    "mimeType": im.get("mimeType"),
    "uri": (im.get("uri") or "")[:80],
    "embedded": "bufferView" in im,
} for im in g.get("images", [])]

node_names = [n.get("name", "") for n in g.get("nodes", [])]
rig_like = [n for n in node_names if any(
    t in n.lower() for t in ("bone", "joint", "arm", "leg", "spine", "hip", "head", "skel", "root")
)]

with zipfile.ZipFile(ZIPF) as z:
    entries = [{"name": i.filename, "size": i.file_size} for i in z.infolist()]
    z.extractall(HERE / "obj_bundle")

fb = FBX.read_bytes()
fb_tokens = {t.decode(): fb.count(t) for t in (
    b"LimbNode", b"Deformer", b"Skin", b"Skeleton", b"BindPose",
    b"Geometry", b"Material", b"Texture", b"Animation",
)}

report = {
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
    "zip_entries": entries,
    "zip_entry_count": len(entries),
    "fbx_bytes": len(fb),
    "fbx_token_counts": fb_tokens,
}
(HERE / "model_inspection.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

print("GLB", meta, flush=True)
print("COUNTS", {k: v for k, v in counts.items() if k != "extensionsUsed"}, flush=True)
print(f"GEOMETRY vertices={vertices} triangles={triangles} primitives={primitives} "
      f"meshes={len(mesh_names)}", flush=True)
print(f"MATERIALS texture_refs={len(texture_refs)} images={len(images)} "
      f"embedded={sum(1 for i in images if i['embedded'])}", flush=True)
print(f"RIG has_skin={report['has_skin']} has_animation={report['has_animation']} "
      f"rig_like_nodes={len(rig_like)}", flush=True)
print(f"ZIP entries={len(entries)}", flush=True)
for e in entries[:12]:
    print(f"  {e['name']} {e['size']} B", flush=True)
print("FBX_TOKENS", fb_tokens, flush=True)
print("INSPECT_OK", flush=True)
