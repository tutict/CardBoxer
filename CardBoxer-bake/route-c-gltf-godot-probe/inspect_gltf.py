"""纯 Python 解析四份 GLB 的 JSON/BIN chunk，不依赖 Blender。

把「glTF 到底带走了什么、丢掉了什么」变成可复算的数字。
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = HERE / "export_report.json"
STRUCT = HERE / "blend_structure.json"
OUT = HERE / "gltf_inspection.json"

GLB_MAGIC = 0x46546C67
JSON_TYPE = 0x4E4F534A
BIN_TYPE = 0x004E4942
TOP_KEYS = ("scenes", "nodes", "meshes", "materials", "textures",
            "images", "samplers", "skins", "animations", "cameras",
            "accessors", "bufferViews", "buffers")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_glb(path: Path):
    data = path.read_bytes()
    magic, version, length = struct.unpack_from("<III", data, 0)
    assert magic == GLB_MAGIC and version == 2, (path.name, magic, version)
    assert length == len(data), (path.name, length, len(data))
    off, chunks = 12, {}
    while off < len(data):
        clen, ctype = struct.unpack_from("<II", data, off)
        off += 8
        chunks[ctype] = data[off:off + clen]
        off += clen
    assert JSON_TYPE in chunks and BIN_TYPE in chunks, path.name
    doc = json.loads(chunks[JSON_TYPE].decode("utf-8"))
    return doc, {"json_bytes": len(chunks[JSON_TYPE]),
                 "bin_bytes": len(chunks[BIN_TYPE])}


def accessor_summary(doc, idx, key=None):
    if idx is None:
        return None
    a = doc["accessors"][idx]
    out = {"count": a.get("count"), "componentType": a.get("componentType"),
           "type": a.get("type")}
    if key in ("POSITION", "NORMAL"):
        out["min"] = a.get("min")
        out["max"] = a.get("max")
    return out


def image_summary(doc):
    rows = []
    bvs = doc.get("bufferViews", [])
    for im in doc.get("images", []):
        bv = im.get("bufferView")
        rows.append({
            "name": im.get("name"),
            "mimeType": im.get("mimeType"),
            "bufferView": bv,
            "bytes": bvs[bv].get("byteLength") if bv is not None else 0,
            "uri": im.get("uri"),
        })
    return rows


def material_summary(doc):
    rows = []
    for m in doc.get("materials", []):
        pbr = m.get("pbrMetallicRoughness", {}) or {}
        rows.append({
            "name": m.get("name"),
            "baseColorTexture": pbr.get("baseColorTexture", {}).get("index"),
            "metallicRoughnessTexture":
                pbr.get("metallicRoughnessTexture", {}).get("index"),
            "normalTexture": (m.get("normalTexture") or {}).get("index"),
            "occlusionTexture": (m.get("occlusionTexture") or {}).get("index"),
            "alphaMode": m.get("alphaMode"),
        })
    return rows


def mesh_summary(doc):
    rows = []
    for m in doc.get("meshes", []):
        for p in m.get("primitives", []):
            attrs = p.get("attributes", {})
            rows.append({
                "mesh": m.get("name"),
                "mode": p.get("mode"),
                "material": p.get("material"),
                "attributes": sorted(attrs.keys()),
                "has_skin_attrs": "JOINTS_0" in attrs and "WEIGHTS_0" in attrs,
                "position": accessor_summary(doc, attrs.get("POSITION"),
                                             "POSITION"),
                "joints": accessor_summary(doc, attrs.get("JOINTS_0")),
                "weights": accessor_summary(doc, attrs.get("WEIGHTS_0")),
            })
    return rows


def main() -> int:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    struct_doc = json.loads(STRUCT.read_text(encoding="utf-8"))
    out_rows = []
    for exp in report["exports"]:
        p = HERE / exp["file"]
        doc, chunks = parse_glb(p)
        counts = {k: len(doc.get(k, [])) for k in TOP_KEYS}
        imgs = image_summary(doc)
        meshes = mesh_summary(doc)
        skins = [{"joints": len(s.get("joints", [])),
                  "inverseBindMatrices": s.get("inverseBindMatrices")}
                 for s in doc.get("skins", [])]
        row = {
            "name": exp["name"], "file": exp["file"],
            "bytes": exp["bytes"], "sha256": sha256(p),
            "description": exp["description"],
            "export_apply": exp["export_apply"],
            "export_materials": exp["export_materials"],
            "glb_chunks": chunks,
            "counts": counts,
            "generator": (doc.get("asset") or {}).get("generator"),
            "extensionsUsed": doc.get("extensionsUsed", []),
            "extensionsRequired": doc.get("extensionsRequired", []),
            "meshes": meshes,
            "skins": skins,
            "animations": [a.get("name") for a in doc.get("animations", [])],
            "materials": material_summary(doc),
            "images": imgs,
            "image_bytes_total": sum(i["bytes"] for i in imgs),
            "vertex_total": sum(m["position"]["count"] or 0
                                for m in meshes if m["position"]),
            "skinned_primitives": sum(1 for m in meshes if m["has_skin_attrs"]),
        }
        assert row["sha256"] == exp["sha256"], exp["file"]
        out_rows.append(row)

    by = {r["name"]: r for r in out_rows}
    stance, posed = by["foe-stance"], by["foe-posed"]
    sp, pp = stance["meshes"][0]["position"], posed["meshes"][0]["position"]
    delta = [round(abs(a - b), 6)
             for a, b in zip(sp["min"] + sp["max"], pp["min"] + pp["max"])]
    pose_delta = {
        "stance_position_min_max": {"min": sp["min"], "max": sp["max"]},
        "posed_position_min_max": {"min": pp["min"], "max": pp["max"]},
        "componentwise_abs_delta": delta,
        "max_abs_delta": max(delta),
        "vertex_count_equal": sp["count"] == pp["count"],
        "skins_stance": stance["counts"]["skins"],
        "skins_posed": posed["counts"]["skins"],
        "animations_stance": stance["counts"]["animations"],
        "animations_posed": posed["counts"]["animations"],
    }
    src_imgs = struct_doc["images"]
    texture_cost = {
        "source_packed_4096_images": len(src_imgs),
        "source_packed_bytes_total": sum(i["packed_bytes"] for i in src_imgs),
        "glb_full_image_count": by["foe-full"]["counts"]["images"],
        "glb_full_image_bytes_total": by["foe-full"]["image_bytes_total"],
        "glb_full_bytes": by["foe-full"]["bytes"],
        "image_share_of_glb": round(
            by["foe-full"]["image_bytes_total"] / by["foe-full"]["bytes"], 4),
    }

    out = {
        "exports": out_rows,
        "pose_delta": pose_delta,
        "texture_cost": texture_cost,
        "source_blend": {"sha256": struct_doc["blend_sha256"],
                         "bytes": struct_doc["blend_bytes"],
                         "action_count": struct_doc["action_count"]},
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for r in out_rows:
        print(f"{r['name']:<16} bytes={r['bytes']:>10} "
              f"meshes={r['counts']['meshes']} skins={r['counts']['skins']} "
              f"anims={r['counts']['animations']} imgs={r['counts']['images']} "
              f"verts={r['vertex_total']} "
              f"skinned={r['skinned_primitives']}")
    print("POSE_DELTA " + json.dumps(pose_delta, ensure_ascii=False))
    print("TEXTURE_COST " + json.dumps(texture_cost, ensure_ascii=False))
    print("GLTF_INSPECTION_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
