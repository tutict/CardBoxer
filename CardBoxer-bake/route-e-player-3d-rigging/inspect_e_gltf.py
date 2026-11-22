"""纯 Python 解析四口径玩家 GLB：结构、PBR 三通道、贴图零重编码、静态快照。

不依赖 Blender；只读 export_e.json 与本工作区的 .glb。
用法：python inspect_e_gltf.py
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "gltf_e_inspection.json"
GLB_MAGIC = 0x46546C67


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_glb(path: Path):
    data = path.read_bytes()
    assert struct.unpack_from("<I", data, 0)[0] == GLB_MAGIC, path
    version, length = struct.unpack_from("<II", data, 4)
    assert version == 2 and length == len(data), (version, length, len(data))
    off, chunks = 12, []
    while off < len(data):
        clen, ctype = struct.unpack_from("<I4s", data, off)
        off += 8
        chunks.append((ctype, data[off:off + clen]))
        off += clen
    js = json.loads(next(p for t, p in chunks if t == b"JSON").decode("utf-8"))
    bin_chunk = next(p for t, p in chunks if t == b"BIN\x00")
    return js, bin_chunk, len(data)


def image_bytes(js, bin_chunk, idx):
    bv = js["bufferViews"][js["images"][idx]["bufferView"]]
    off = bv.get("byteOffset", 0)
    return bin_chunk[off:off + bv["byteLength"]]


def primitives(js):
    out = []
    for mi, mesh in enumerate(js.get("meshes", [])):
        for pi, prim in enumerate(mesh.get("primitives", [])):
            attrs = sorted(prim.get("attributes", {}).keys())
            acc = js["accessors"][prim["attributes"]["POSITION"]]
            out.append({"mesh": mi, "primitive": pi,
                        "attributes": attrs,
                        "verts": acc["count"],
                        "pos_min": acc.get("min"), "pos_max": acc.get("max")})
    return out


def main() -> int:
    exp = json.loads((HERE / "export_e.json").read_text(encoding="utf-8"))
    packed = exp["packed_images"]
    rows = []
    for item in exp["exports"]:
        path = HERE / item["file"]
        js, bin_chunk, file_len = parse_glb(path)
        imgs = js.get("images", [])
        img_rows = []
        for i in range(len(imgs)):
            blob = image_bytes(js, bin_chunk, i)
            hit = [p for p in packed if p["sha256"] == sha(blob)]
            img_rows.append({"index": i, "bytes": len(blob),
                             "sha256": sha(blob),
                             "matches_packed_source": bool(hit),
                             "source_name": hit[0]["name"] if hit else None})
        mats = js.get("materials", [])
        pbr = {}
        for m in mats:
            b = m.get("pbrMetallicRoughness", {})
            pbr = {
                "baseColorTexture": b.get("baseColorTexture", {}).get("index"),
                "metallicRoughnessTexture": b.get(
                    "metallicRoughnessTexture", {}).get("index"),
                "normalTexture": m.get("normalTexture", {}).get("index"),
            }
            break
        rows.append({
            "name": item["name"], "file": item["file"],
            "file_bytes": file_len, "sha256": item["sha256"],
            "counts": {k: len(js.get(k, [])) for k in
                       ("scenes", "nodes", "meshes", "materials", "textures",
                        "images", "skins", "animations", "cameras",
                        "accessors", "bufferViews", "buffers")},
            "extensionsUsed": js.get("extensionsUsed", []),
            "skin_joints": [len(s.get("joints", []))
                            for s in js.get("skins", [])],
            "primitives": primitives(js),
            "images": img_rows,
            "pbr": pbr,
            "export_apply": item["export_apply"],
        })

    # 静态快照：站架 vs cross#10 的 POSITION min/max 最大分量差
    def bounds(name):
        r = next(x for x in rows if x["name"] == name)
        return r["primitives"][0]["pos_min"], r["primitives"][0]["pos_max"]
    s_min, s_max = bounds("player-stance")
    c_min, c_max = bounds("player-cross")
    delta = max([abs(a - b) for a, b in zip(s_min, c_min)]
                + [abs(a - b) for a, b in zip(s_max, c_max)])

    full = next(x for x in rows if x["name"] == "player-full")
    out = {
        "exports": rows,
        "packed_source_images": packed,
        "zero_reencode": {
            "full_images": len(full["images"]),
            "all_match": bool(full["images"])
            and all(i["matches_packed_source"] for i in full["images"]),
            "source_bytes": sum(p["bytes"] for p in packed),
            "glb_image_bytes": sum(i["bytes"] for i in full["images"]),
            "share_of_full_glb": round(
                sum(i["bytes"] for i in full["images"]) / full["file_bytes"], 5),
        },
        "static_snapshot": {
            "stance_pos_min": s_min, "stance_pos_max": s_max,
            "cross_pos_min": c_min, "cross_pos_max": c_max,
            "max_component_delta_m": round(delta, 6),
            "stance_skins": next(x for x in rows
                                 if x["name"] == "player-stance")["counts"]["skins"],
            "stance_animations": next(x for x in rows
                                      if x["name"] == "player-stance")["counts"]["animations"],
        },
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for r in rows:
        c = r["counts"]
        print(f"{r['name']:<20} bytes={r['file_bytes']:>10} "
              f"meshes={c['meshes']} skins={c['skins']} "
              f"anims={c['animations']} imgs={c['images']} "
              f"prims={len(r['primitives'])}")
    z = out["zero_reencode"]
    print(f"ZERO_REENCODE all_match={z['all_match']} "
          f"src={z['source_bytes']} glb={z['glb_image_bytes']} "
          f"share={z['share_of_full_glb']}")
    print(f"STATIC_SNAPSHOT max_delta={delta:.6f}m "
          f"skins={out['static_snapshot']['stance_skins']} "
          f"anims={out['static_snapshot']['stance_animations']}")
    print("GLTF_INSPECT_E_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
