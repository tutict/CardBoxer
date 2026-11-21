"""H 路线 P1：给对手怪高模补平滑 skin，导出 Godot 能驱动的 GLB。

链路与 F 路线 build_rigged_glb.py 同构：
  A 路线 .blend 的 a_continuous_shell（3 壳 / ARMATURE_AUTO 平滑权重）
  → DATA_TRANSFER 回传 node_0 原高模 → 加 ARMATURE modifier
  → export_apply=False 只导出「高模 + 13 骨」。

不能直接用 node_0 自带的 13 组权重：那是 11-08 的**刚性权重**
（拓扑修复探针V1 实测 35° 驱动右臂撕裂），A 路线正是用
SURFACE_DEFORM 绕开它。这里回传的是代理壳的平滑权重。

只读 A 路线 .blend，不回写任何归档。
用法：blender.exe -b --python build_foe_rigged_h.py
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
BLEND = BAKE / "A路线-资产重做" / "对手怪-可变形连续壳.blend"
OUT_GLB = HERE / "foe-rigged.glb"
OUT_JSON = HERE / "data" / "foe_rigged_build.json"


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
                                "size": list(n.image.size)})
    return sorted(out, key=lambda d: d["image"])


def fresh_copy(src, name):
    obj = src.copy()
    obj.data = src.data.copy()
    bpy.context.scene.collection.objects.link(obj)
    obj.name = name
    for m in list(obj.modifiers):
        obj.modifiers.remove(m)
    obj.vertex_groups.clear()
    obj.parent = None
    obj.hide_render = True
    return obj


def main() -> int:
    assert BLEND.is_file(), BLEND
    blend_sha = sha256(BLEND)
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    scene = bpy.context.scene

    src = next(o for o in scene.objects
               if o.type == "MESH"
               and any(m.type == "SURFACE_DEFORM" for m in o.modifiers))
    shell = next(m for m in src.modifiers
                 if m.type == "SURFACE_DEFORM").target
    rig = next(o for o in scene.objects if o.type == "ARMATURE")

    src_uv = len(src.data.uv_layers)
    src_tex = textures(src)
    bone_names = [b.name for b in rig.data.bones]
    shell_groups = [g.name for g in shell.vertex_groups]
    log("OPEN", src.name, len(src.data.vertices), "verts /",
        shell.name, len(shell.data.vertices), "verts /",
        rig.name, len(bone_names), "bones")
    assert set(bone_names) == set(shell_groups), (bone_names, shell_groups)

    final = fresh_copy(src, "foe_HI_skinned")
    for name in bone_names:
        final.vertex_groups.new(name=name)

    mod = final.modifiers.new("weights_from_continuous_shell",
                              "DATA_TRANSFER")
    mod.object = shell
    mod.use_vert_data = True
    mod.data_types_verts = {"VGROUP_WEIGHTS"}
    mod.vert_mapping = "POLYINTERP_NEAREST"
    mod.layers_vgroup_select_src = "ALL"
    mod.layers_vgroup_select_dst = "NAME"
    bpy.ops.object.select_all(action="DESELECT")
    final.select_set(True)
    bpy.context.view_layer.objects.active = final
    bpy.ops.object.modifier_apply(modifier=mod.name)

    arm_mod = final.modifiers.new("foe_rig", "ARMATURE")
    arm_mod.object = rig

    covered = sum(1 for v in final.data.vertices
                  if any(g.weight > 1e-6 for g in v.groups))
    total = len(final.data.vertices)
    coverage = covered / total
    log("WEIGHTS", covered, "/", total, round(coverage * 100, 4), "%")
    assets = {
        "uv_layers": len(final.data.uv_layers),
        "materials": len(final.data.materials),
        "textures": textures(final),
        "uv_same": len(final.data.uv_layers) == src_uv,
        "textures_same": textures(final) == src_tex,
    }
    log("ASSETS", assets)
    assert assets["uv_same"] and assets["textures_same"]
    assert coverage > 0.99, covered

    bpy.ops.object.select_all(action="DESELECT")
    final.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = final
    result = bpy.ops.export_scene.gltf(
        filepath=str(OUT_GLB),
        export_format="GLB",
        use_selection=True,
        export_apply=False,          # 关键：不烘焙 ARMATURE，保留 skin
        export_skins=True,
        export_animations=False,
        export_materials="EXPORT",
        export_yup=True,
        export_cameras=False,
        export_lights=False,
    )
    log("EXPORT", list(result), OUT_GLB.stat().st_size, "B")
    assert list(result) == ["FINISHED"]
    assert OUT_GLB.is_file() and OUT_GLB.stat().st_size > 1_000_000

    report = {
        "blender": bpy.app.version_string,
        "source_blend": str(BLEND),
        "source_blend_sha256": blend_sha,
        "source": {"object": src.name, "verts": len(src.data.vertices),
                   "uv_layers": src_uv, "textures": src_tex,
                   "vertex_groups_before": len(src.vertex_groups)},
        "weight_source": {"object": shell.name,
                          "verts": len(shell.data.vertices),
                          "groups": shell_groups},
        "rig": {"object": rig.name, "bones": bone_names},
        "skinned": {"object": final.name, "verts": total,
                    "weighted_verts": covered,
                    "coverage_pct": round(coverage * 100, 4),
                    "assets": assets,
                    "modifiers": [{"name": m.name, "type": m.type}
                                  for m in final.modifiers]},
        "export": {"file": OUT_GLB.name,
                   "bytes": OUT_GLB.stat().st_size,
                   "sha256": sha256(OUT_GLB),
                   "export_apply": False,
                   "export_skins": True,
                   "operator_result": list(result)},
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2)
                        + "\n", encoding="utf-8")
    log("FOE_RIGGED_GLB_OK", report["skinned"]["coverage_pct"], "%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
