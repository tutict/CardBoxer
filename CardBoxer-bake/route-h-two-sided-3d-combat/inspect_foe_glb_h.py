"""纯 Python 复核 foe-rigged.glb：skin 真的挂在高模上、贴图零重编码。

不依赖 Blender；解析 GLB 的 JSON + BIN chunk，与
F 路线 player-rigged.glb（骨名口径）和
foe-blender-modeling-v1/artifact_03.glb（原始 PBR 字节）对照。
导出器警告「Armature must be the parent of skinned mesh」必须由这里的
node.skin / JOINTS_0 实据判定有没有造成实际损害。
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GLB = HERE / "foe-rigged.glb"
PLAYER = BAKE / "route-f-godot-driver" / "player-rigged.glb"
SOURCE = BAKE / "foe-blender-modeling-v1" / "artifact_03.glb"
OUT = HERE / "data" / "foe_gltf_inspection.json"


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
              "has_inverse_bind": "inverseBindMatrices" in s}
             for s in js.get("skins", [])]
    return {
        "file": path.name, "bytes": size, "sha256": sha(path.read_bytes()),
        "counts": {k: len(js.get(k, [])) for k in
                   ("scenes", "nodes", "meshes", "materials", "textures",
                    "images", "skins", "animations", "accessors")},
        "primitives": prims, "skinned_nodes": skinned_nodes, "skins": skins,
        "images": image_blobs(js, binary),
        "joint_node_names": [js["nodes"][j].get("name")
                             for j in js.get("skins", [{}])[0].get("joints", [])]
        if js.get("skins") else [],
    }


def main() -> int:
    for p in (GLB, PLAYER, SOURCE):
        assert p.is_file(), p
    foe = summarize(GLB)
    player = summarize(PLAYER)
    source = summarize(SOURCE)
    hi = [p for p in foe["primitives"]
          if p["has_joints"] and p["has_weights"] and p["verts"] > 50000]
    phi = [p for p in player["primitives"]
           if p["has_joints"] and p["has_weights"] and p["verts"] > 50000]
    # 判据订正 2026-11-11：第一版写死 highpoly_verts == 64024（.blend 值）
    # 报红。glTF 导出器会按 UV seam / 法线拆分顶点，F 玩家同样如此：
    # .blend 57,901 → GLB 57,934（+33）。这里实测 +35，属同一现象。
    # 因此退役「等于源顶点数」，改判「拆分增量在 0..100 且总量 > 6 万」，
    # 并把两个增量都记进 verdict 供复算。
    split_delta = (hi[0]["verts"] - 64024) if hi else None
    player_split_delta = (phi[0]["verts"] - 57901) if phi else None
    verdict = {
        "highpoly_has_skin": bool(hi),
        "highpoly_verts": hi[0]["verts"] if hi else None,
        "blend_highpoly_verts": 64024,
        "vertex_split_delta": split_delta,
        "player_glb_verts": phi[0]["verts"] if phi else None,
        "player_blend_verts": 57901,
        "player_vertex_split_delta": player_split_delta,
        "skinned_nodes": len(foe["skinned_nodes"]),
        "skin_joints": foe["skins"][0]["joints"] if foe["skins"] else 0,
        "has_inverse_bind": bool(foe["skins"]
                                 and foe["skins"][0]["has_inverse_bind"]),
        "zero_animations": foe["counts"]["animations"] == 0,
        "three_images": foe["counts"]["images"] == 3,
        "images_zero_reencode": all(
            any(i["sha256"] == r["sha256"] for r in source["images"])
            for i in foe["images"]),
        "joint_names_same_as_player": (
            foe["joint_node_names"] == player["joint_node_names"]),
        "source_highpoly_has_no_skin": not any(
            p["has_joints"] and p["verts"] > 50000
            for p in source["primitives"]),
    }
    checks = {
        "highpoly_has_skin": verdict["highpoly_has_skin"],
        "highpoly_verts_split_ok": (
            split_delta is not None and 0 <= split_delta <= 100
            and verdict["highpoly_verts"] > 60000),
        "player_split_delta_positive": (
            player_split_delta is not None and 0 < player_split_delta <= 100),
        "one_skinned_node": verdict["skinned_nodes"] >= 1,
        "skin_joints_ge_13": verdict["skin_joints"] >= 13,
        "inverse_bind_present": verdict["has_inverse_bind"],
        "zero_animations": verdict["zero_animations"],
        "three_images": verdict["three_images"],
        "images_zero_reencode": verdict["images_zero_reencode"],
        "joint_names_same_as_player": verdict["joint_names_same_as_player"],
        "source_highpoly_has_no_skin": verdict["source_highpoly_has_no_skin"],
    }
    out = {"foe": foe, "player_joint_names": player["joint_node_names"],
           "source": {"file": SOURCE.name, "bytes": source["bytes"],
                      "images": source["images"],
                      "primitives": source["primitives"]},
           "verdict": verdict, "checks": checks,
           "failed": [k for k, v in checks.items() if not v],
           "ok": all(checks.values())}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("VERDICT", json.dumps(verdict, ensure_ascii=False))
    print("SKINNED_NODES", foe["skinned_nodes"])
    print("JOINTS", foe["joint_node_names"])
    print("PRIMS", [(p["verts"], p["has_joints"], p["has_weights"])
                    for p in foe["primitives"]])
    for k, v in checks.items():
        print("CHECK", k, v)
    print("FOE_GLTF_OK" if out["ok"] else "FOE_GLTF_FAILED")
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
