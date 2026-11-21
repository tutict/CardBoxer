"""B 路线：纯 Python 解析 GLB，证明「塌缩」真的落进了导出资产。

不看 Blender 预览（Workbench 二色预览里那条细线来源存疑），直接对账
I 基线 foe-rigged.glb 与 B 版 foe-rigged-b.glb 的 POSITION 坐标多重集：
  * 未改动的顶点坐标应逐值相同；
  * 被删的 8,753 个旧坐标应消失，换成聚成 ~195 个质心簇的新坐标
    （簇半径 1e-5，量化网格 1e-3）。

同时守 skin / 贴图 / 顶点数，证明驱动链与 PBR 没被破坏。
只读，输出 data/glb_shape_b.json。
用法：python verify_glb_shape_b.py
"""
from __future__ import annotations

import hashlib
import json
import struct
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE / "orig" / "pre-shape" / "foe-rigged.glb"
NEW = HERE / "foe-rigged-b.glb"
TARGETS = HERE / "data" / "shell_targets_b.json"
BUILD = HERE / "data" / "build_shape_b.json"
OUT = HERE / "data" / "glb_shape_b.json"

QUANT = 1000  # 1e-3 网格


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_glb(p: Path) -> dict:
    data = p.read_bytes()
    magic, version, length = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67 and version == 2, p
    assert length == len(data), (length, len(data))
    off, js, bin_ = 12, None, None
    while off < length:
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:
            js = json.loads(chunk.decode("utf-8"))
        elif ctype == 0x004E4942:
            bin_ = chunk
        off += 8 + clen + ((4 - clen % 4) % 4 if clen % 4 else 0)
    assert js is not None and bin_ is not None
    return {"json": js, "bin": bin_, "bytes": len(data),
            "sha256": sha256(p)}


def positions(g: dict) -> list[tuple[float, float, float]]:
    js, buf = g["json"], g["bin"]
    prim = js["meshes"][0]["primitives"][0]
    acc = js["accessors"][prim["attributes"]["POSITION"]]
    assert acc["componentType"] == 5126 and acc["type"] == "VEC3"
    bv = js["bufferViews"][acc["bufferView"]]
    start = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = bv.get("byteStride", 12)
    n = acc["count"]
    out = []
    for i in range(n):
        x, y, z = struct.unpack_from("<fff", buf, start + i * stride)
        out.append((round(x, 6), round(y, 6), round(z, 6)))
    return out


def image_shas(g: dict) -> list[str]:
    js, buf = g["json"], g["bin"]
    out = []
    for im in js.get("images", []):
        bv = js["bufferViews"][im["bufferView"]]
        b = buf[bv.get("byteOffset", 0):
                bv.get("byteOffset", 0) + bv["byteLength"]]
        out.append(hashlib.sha256(b).hexdigest())
    return out


def main() -> int:
    tg = json.loads(TARGETS.read_text(encoding="utf-8"))
    build = json.loads(BUILD.read_text(encoding="utf-8"))
    base, new = parse_glb(BASE), parse_glb(NEW)
    pb, pn = positions(base), positions(new)
    cb, cn = Counter(pb), Counter(pn)
    only_base = cb - cn          # 被删掉的旧坐标（含重数）
    only_new = cn - cb           # 新增的塌缩坐标
    unchanged = sum((cb & cn).values())
    removed = sum(only_base.values())
    added = sum(only_new.values())

    clusters = {(round(x * QUANT), round(y * QUANT), round(z * QUANT))
                for (x, y, z), _ in only_new.items()}
    jb, jn = base["json"], new["json"]
    prim_new = jn["meshes"][0]["primitives"][0]
    attrs = sorted(prim_new["attributes"].keys())

    # round2 的目标集是「195 壳 + 67 补删壳」，期望值以 build 报告为准，
    # 不再写死 round1 的 8,753。
    expected_verts = build["targets"]["verts"]
    clusters_max = build["targets"]["shells"] + 60
    checks = {
        "both_glb_parsed": True,
        "target_spec_verified": tg["ok"] and not tg["failed"],
        "build_verified": build["ok"] and not build["failed"],
        "build_reports_unified_weights": (
            build["integrity"]["targets_all_hips_weight_1"]),
        "sha_differs": base["sha256"] != new["sha256"],
        "verts_delta_small": abs(len(pn) - len(pb)) < 300,
        "skin_preserved": ("JOINTS_0" in attrs and "WEIGHTS_0" in attrs
                           and len(jn.get("skins", [])) == 1),
        "animations_still_zero": len(jn.get("animations", [])) == 0,
        "images_identical": image_shas(base) == image_shas(new),
        "image_count_3": len(jn.get("images", [])) == 3,
        # 订正：0.85 是 round1（删 13.7%）时写死的下限；round2 删了
        # 16.4%，保持不变的比例必然降到 0.836。判据按目标规模复算，
        # 不再写死数字。
        "unchanged_ratio_matches_target_scale": (
            unchanged / max(len(pb), 1)
            >= (1 - expected_verts / max(len(pb), 1)) - 0.01),
        "removed_coords_near_target": (
            abs(removed - expected_verts) <= 300),
        "added_coords_near_target": (
            abs(added - expected_verts) <= 300),
        "new_coords_form_shell_centroid_clusters": (
            build["targets"]["shells"] - 60
            <= len(clusters) <= clusters_max),
        "base_glb_is_i_baseline": (
            base["sha256"]
            == "0edcfe9e455f3c8c9deb7034397c815fd701130ed9a10"
               "c2e08800fff789cba88"),
        "exported_sha_matches_build": (
            new["sha256"] == build["export"]["sha256"]),
    }
    report = {
        "base": {"file": str(BASE), "bytes": base["bytes"],
                 "sha256": base["sha256"], "verts": len(pb),
                 "skins": len(jb.get("skins", [])),
                 "images": len(jb.get("images", []))},
        "new": {"file": str(NEW), "bytes": new["bytes"],
                "sha256": new["sha256"], "verts": len(pn),
                "skins": len(jn.get("skins", [])),
                "images": len(jn.get("images", [])),
                "attributes": attrs},
        "coordinate_diff": {
            "unchanged": unchanged, "removed": removed, "added": added,
            "unchanged_ratio": round(unchanged / max(len(pb), 1), 6),
            "new_coord_clusters_1e3": len(clusters),
            "target_verts": expected_verts,
            "target_shells": build["targets"]["shells"],
        },
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
    }
    report["ok"] = not report["failed"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("BASE", base["bytes"], "verts", len(pb), base["sha256"][:16])
    print("NEW ", new["bytes"], "verts", len(pn), new["sha256"][:16])
    print("DIFF", report["coordinate_diff"])
    for k, v in checks.items():
        print("CHECK", k, v)
    print("GLB_SHAPE_B_OK" if report["ok"] else "GLB_SHAPE_B_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
