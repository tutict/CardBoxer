"""纯 Python 复核 player-rigged.glb：skin 是否真的挂在高模上。

不依赖 Blender；解析 GLB 的 JSON chunk + BIN chunk，逐项验证
primitive 属性、skin joints、贴图零重编码，并与 E 路线 player-full.glb
对照。导出器警告「Armature must be the parent of skinned mesh」必须由
这里的 node.skin / JOINTS_0 实据来判定有没有造成实际损害。
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
E = BAKE / "route-e-player-3d-rigging"
GLB = HERE / "player-rigged.glb"
REF = E / "player-full.glb"
OUT = HERE / "data" / "rigged_gltf_inspection.json"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def parse(path: Path):
    data = path.read_bytes()
    assert struct.unpack_from("<I", data, 0)[0] == 0x46546C67, path
    version, length = struct.unpack_from("<II", data, 4)
    assert version == 2 and length == len(data)
    off, chunks = 12, []
    while off < len(data):
        clen, ctype = struct.unpack_from("<I4s", data, off)
        off += 8
        chunks.append((ctype, data[off:off + clen]))
        off += clen
    js = json.loads(next(p for t, p in chunks if t == b"JSON").decode("utf-8"))
    binary = next(p for t, p in chunks if t == b"BIN\x00")
    return js, binary, len(data)


def image_blobs(js, binary):
    out = []
    for i, im in enumerate(js.get("images", [])):
        bv = js["bufferViews"][im["bufferView"]]
        off = bv.get("byteOffset", 0)
        blob = binary[off:off + bv["byteLength"]]
        out.append({"index": i, "bytes": len(blob), "sha256": sha(blob),
                    "name": im.get("name")})
    return out


def summarize(path: Path) -> dict:
    js, binary, size = parse(path)
    prims = []
    for mi, mesh in enumerate(js.get("meshes", [])):
        for pi, prim in enumerate(mesh.get("primitives", [])):
            acc = js["accessors"][prim["attributes"]["POSITION"]]
            prims.append({
                "mesh": mi, "primitive": pi,
                "attributes": sorted(prim["attributes"].keys()),
                "verts": acc["count"],
                "has_joints": "JOINTS_0" in prim["attributes"],
                "has_weights": "WEIGHTS_0" in prim["attributes"],
                "pos_min": acc.get("min"), "pos_max": acc.get("max"),
            })
    skinned_nodes = [
        {"node": i, "name": n.get("name"),
         "skin": n.get("skin"), "mesh": n.get("mesh")}
        for i, n in enumerate(js.get("nodes", []))
        if "skin" in n]
    skins = [{"joints": len(s.get("joints", [])),
              "inverse_bind": len(s.get("inverseBindMatrices", [])) if isinstance(
                  s.get("inverseBindMatrices"), list) else "accessor"}
             for s in js.get("skins", [])]
    return {
        "file": path.name, "bytes": size, "sha256": sha(path.read_bytes()),
        "counts": {k: len(js.get(k, [])) for k in
                   ("scenes", "nodes", "meshes", "materials", "textures",
                    "images", "skins", "animations", "accessors")},
        "primitives": prims,
        "skinned_nodes": skinned_nodes,
        "skins": skins,
        "images": image_blobs(js, binary),
        "joint_node_names": [js["nodes"][j].get("name")
                             for j in js.get("skins", [{}])[0].get("joints", [])]
        if js.get("skins") else [],
    }


def main() -> int:
    rigged = summarize(GLB)
    ref = summarize(REF)
    out = {"rigged": rigged, "reference_player_full": ref,
           "verdict": {}}
    skinned_hi = [p for p in rigged["primitives"]
                  if p["has_joints"] and p["verts"] > 50000]
    out["verdict"] = {
        "highpoly_has_skin": bool(skinned_hi),
        "highpoly_verts": skinned_hi[0]["verts"] if skinned_hi else None,
        "skinned_nodes": len(rigged["skinned_nodes"]),
        "skin_joints": rigged["skins"][0]["joints"] if rigged["skins"] else 0,
        "images_zero_reencode": all(
            any(i["sha256"] == r["sha256"] for r in ref["images"])
            for i in rigged["images"]),
        "reference_highpoly_has_skin": any(
            p["has_joints"] and p["verts"] > 50000
            for p in ref["primitives"]),
    }
    v = out["verdict"]
    ok = (v["highpoly_has_skin"] and v["skinned_nodes"] >= 1
          and v["skin_joints"] >= 13
          and v["images_zero_reencode"]
          and not v["reference_highpoly_has_skin"])
    out["ok"] = ok
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("RIGGED", json.dumps(v, ensure_ascii=False))
    print("SKINNED_NODES", rigged["skinned_nodes"])
    print("JOINTS", rigged["joint_node_names"])
    print("PRIMS", [(p["verts"], p["has_joints"]) for p in
                    rigged["primitives"]])
    print("RIGGED_GLTF_OK" if ok else "RIGGED_GLTF_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
