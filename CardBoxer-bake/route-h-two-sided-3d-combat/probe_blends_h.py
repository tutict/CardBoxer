"""H 路线 P0：判定 A 路线对手怪 .blend 能否复用 F 的「权重回传 → GLB」链。

只读两个 .blend，逐个 dump 对象 / modifier / vertex group / 13 骨 rest /
UV / 贴图 / bbox，最后逐骨比对 rest matrix 与骨名。
用法：blender.exe -b --python probe_blends_h.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import bpy

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
OUT = HERE / "data" / "blend_probe_h.json"
BLENDS = {
    "foe": BAKE / "route-a-asset-rework" / "foe-deformable-continuous-shell.blend",
    "player": BAKE / "route-e-player-3d-rigging" / "player-V4b-deformable-continuous-shell.blend",
}


def log(*a):
    print(*a, flush=True)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def textures(obj) -> list[dict]:
    out = []
    for slot in obj.material_slots:
        mat = slot.material
        if mat and mat.use_nodes:
            for n in mat.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image:
                    out.append({"image": n.image.name,
                                "size": list(n.image.size),
                                "packed": n.image.packed_file is not None})
    return sorted(out, key=lambda d: d["image"])


def mesh_info(o) -> dict:
    groups = []
    for g in o.vertex_groups:
        groups.append({"name": g.name, "index": g.index})
    covered = sum(1 for v in o.data.vertices
                  if any(w.weight > 1e-6 for w in v.groups))
    return {
        "name": o.name, "type": o.type,
        "verts": len(o.data.vertices), "faces": len(o.data.polygons),
        "uv_layers": [u.name for u in o.data.uv_layers],
        "materials": [m.name if m else None for m in o.data.materials],
        "textures": textures(o),
        "vertex_groups": groups,
        "weighted_verts": covered,
        "modifiers": [
            {"name": m.name, "type": m.type,
             "target": (m.target.name if m.type in {"SURFACE_DEFORM", "ARMATURE",
                                                    "DATA_TRANSFER"}
                         and getattr(m, "target", None) else None),
             "object": (m.object.name if m.type in {"ARMATURE", "DATA_TRANSFER"}
                        and getattr(m, "object", None) else None)}
            for m in o.modifiers],
        "dimensions": [round(float(x), 6) for x in o.dimensions],
        "location": [round(float(x), 6) for x in o.location],
        "scale": [round(float(x), 6) for x in o.scale],
        "parent": o.parent.name if o.parent else None,
    }


def rig_info(o) -> dict:
    bones = []
    for b in o.data.bones:
        bones.append({
            "name": b.name,
            "parent": b.parent.name if b.parent else None,
            "head": [round(float(x), 6) for x in b.head_local],
            "tail": [round(float(x), 6) for x in b.tail_local],
            "matrix_local": [round(float(x), 6)
                             for row in b.matrix_local for x in row],
        })
    return {"name": o.name, "bones": bones,
            "location": [round(float(x), 6) for x in o.location],
            "scale": [round(float(x), 6) for x in o.scale]}


def dump(tag: str, path: Path) -> dict:
    assert path.is_file(), path
    bpy.ops.wm.open_mainfile(filepath=str(path))
    scene = bpy.context.scene
    meshes = [mesh_info(o) for o in scene.objects if o.type == "MESH"]
    rigs = [rig_info(o) for o in scene.objects if o.type == "ARMATURE"]
    hi = [m for m in meshes if any(x["type"] == "SURFACE_DEFORM"
                                  for x in m["modifiers"])]
    shells = [m for m in meshes if any(x["type"] == "ARMATURE"
                                       for x in m["modifiers"])]
    return {
        "blend": str(path), "sha256": sha256(path),
        "blender": bpy.app.version_string,
        "objects": [{"name": o.name, "type": o.type}
                    for o in scene.objects],
        "meshes": meshes, "rigs": rigs,
        "highpoly": [m["name"] for m in hi],
        "shells": [m["name"] for m in shells],
    }


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = {tag: dump(tag, p) for tag, p in BLENDS.items()}
    foe_rig = data["foe"]["rigs"][0] if data["foe"]["rigs"] else None
    pl_rig = data["player"]["rigs"][0] if data["player"]["rigs"] else None
    checks = {}
    facts = {}
    if foe_rig and pl_rig:
        fn = [b["name"] for b in foe_rig["bones"]]
        pn = [b["name"] for b in pl_rig["bones"]]
        checks["bone_names_identical"] = fn == pn
        checks["bone_count_13"] = len(fn) == 13 and len(pn) == 13
        # 判据订正 2026-11-11：rest 不同不是「链不可用」的失败，
        # 而是本探针的**发现**——它决定对手怪必须有自己的 apose_points
        # （RigDriver 拿它当旋转中心 hv）。写进 facts，不进 checks，
        # 避免把「事实」当成「要修的红灯」。
        facts["rest_matrix_identical"] = all(
            a["matrix_local"] == b["matrix_local"]
            for a, b in zip(foe_rig["bones"], pl_rig["bones"]))
        facts["max_bone_head_delta_m"] = max(
            round(sum((x - y) ** 2 for x, y in
                      zip(a["head"], b["head"])) ** 0.5, 6)
            for a, b in zip(foe_rig["bones"], pl_rig["bones"]))
        facts["consequence"] = (
            "foe needs its own apose_points; see make_foe_motion_h.py")
        checks["rig_transform_identical"] = (
            foe_rig["location"] == pl_rig["location"]
            and foe_rig["scale"] == pl_rig["scale"])
    checks["foe_has_surfdeform"] = bool(data["foe"]["highpoly"])
    checks["foe_has_armature_shell"] = bool(data["foe"]["shells"])
    checks["player_has_surfdeform"] = bool(data["player"]["highpoly"])
    for tag in ("foe", "player"):
        hi = [m for m in data[tag]["meshes"]
              if m["name"] in data[tag]["highpoly"]]
        if hi:
            checks[f"{tag}_one_uv"] = len(hi[0]["uv_layers"]) == 1
            checks[f"{tag}_three_textures"] = len(hi[0]["textures"]) == 3
            checks[f"{tag}_4096_pbr"] = all(
                t["size"] == [4096, 4096] for t in hi[0]["textures"])
            checks[f"{tag}_textures_packed"] = all(
                t["packed"] for t in hi[0]["textures"])
    report = {"blends": data, "checks": checks, "facts": facts,
              "failed": [k for k, v in checks.items() if not v],
              "ok": all(checks.values()) and len(checks) >= 10}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for tag, d in data.items():
        log("BLEND", tag, Path(d["blend"]).name, d["sha256"][:12],
            "objects=", len(d["objects"]))
        for m in d["meshes"]:
            log("  MESH", m["name"], m["verts"], "verts",
                "groups=", len(m["vertex_groups"]),
                "weighted=", m["weighted_verts"],
                "mods=", [x["type"] for x in m["modifiers"]],
                "uv=", len(m["uv_layers"]), "tex=", len(m["textures"]))
        for r in d["rigs"]:
            log("  RIG", r["name"], len(r["bones"]), "bones",
                [b["name"] for b in r["bones"]][:4], "...")
    for k, v in checks.items():
        log("CHECK", k, v)
    for k, v in facts.items():
        log("FACT", k, v)
    log("BLEND_PROBE_OK" if report["ok"] else "BLEND_PROBE_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
