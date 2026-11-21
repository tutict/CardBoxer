"""H 路线：比对两份 GLB 的贴图字节与 POSITION bbox，判定是否内容串味。"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
PAIR = {
    "player": BAKE / "F路线-Godot驱动层" / "player-rigged.glb",
    "foe": HERE / "foe-rigged.glb",
}
OUT = HERE / "data" / "glb_pair_h.json"


def parse(p: Path):
    data = p.read_bytes()
    assert struct.unpack_from("<I", data, 0)[0] == 0x46546C67
    off, chunks = 12, []
    while off < len(data):
        clen, ctype = struct.unpack_from("<I4s", data, off)
        off += 8
        chunks.append((ctype, data[off:off + clen]))
        off += clen
    js = json.loads(next(c for t, c in chunks if t == b"JSON").decode("utf-8"))
    binary = next(c for t, c in chunks if t == b"BIN\x00")
    return js, binary, len(data)


def main() -> int:
    out = {}
    for tag, p in PAIR.items():
        js, binary, size = parse(p)
        images = []
        for im in js.get("images", []):
            bv = js["bufferViews"][im["bufferView"]]
            off = bv.get("byteOffset", 0)
            blob = binary[off:off + bv["byteLength"]]
            images.append({"name": im.get("name"), "bytes": len(blob),
                           "sha256": hashlib.sha256(blob).hexdigest()})
        prim = js["meshes"][0]["primitives"][0]
        acc = js["accessors"][prim["attributes"]["POSITION"]]
        out[tag] = {"file": p.name, "bytes": size,
                    "images": images, "verts": acc["count"],
                    "pos_min": acc.get("min"), "pos_max": acc.get("max"),
                    "skin_joints": len(js["skins"][0]["joints"])
                    if js.get("skins") else 0}
    psha = {x["sha256"] for x in out["player"]["images"]}
    fsha = {x["sha256"] for x in out["foe"]["images"]}
    report = {"pair": out,
              "image_sets_identical": psha == fsha,
              "shared_image_count": len(psha & fsha),
              "bbox_different": (out["player"]["pos_min"] != out["foe"]["pos_min"]
                                 or out["player"]["pos_max"]
                                 != out["foe"]["pos_max"]),
              "verts_different": out["player"]["verts"] != out["foe"]["verts"]}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for tag, d in out.items():
        print(tag, d["file"], d["bytes"], "B verts=", d["verts"],
              "bbox=", d["pos_min"], d["pos_max"])
        for i in d["images"]:
            print("   IMG", i["name"], i["bytes"], i["sha256"][:16])
    print("image_sets_identical", report["image_sets_identical"],
          "shared", report["shared_image_count"],
          "bbox_different", report["bbox_different"],
          "verts_different", report["verts_different"])
    print("GLB_PAIR_DISTINCT_OK" if (not report["image_sets_identical"]
                                    and report["bbox_different"]
                                    and report["verts_different"])
          else "GLB_PAIR_SUSPICIOUS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
