"""Blender 侧只读诊断：导出 glTF 之前先把「哪些东西能带出去」量清楚。

不保存 .blend，不回写 A 路线归档，不改游戏工程。
用法：blender.exe -b --python probe_blend_structure.py
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import hashlib
import json
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
BLEND = BAKE / "A路线-资产重做" / "对手怪-可变形连续壳.blend"
OUT = HERE / "blend_structure.json"


def log(*a):
    print(*a, flush=True)


def main() -> int:
    assert BLEND.is_file(), BLEND
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    scene = bpy.context.scene

    objects = []
    for o in sorted(scene.objects, key=lambda x: x.name):
        row = {
            "name": o.name, "type": o.type,
            "hide_render": bool(o.hide_render),
            "modifiers": [{"name": m.name, "type": m.type,
                           "target": getattr(getattr(m, "target", None),
                                             "name", None),
                           "is_bound": bool(getattr(m, "is_bound", False))}
                          for m in o.modifiers],
            "vertex_groups": len(o.vertex_groups) if o.type == "MESH" else 0,
        }
        if o.type == "MESH":
            row.update({
                "verts": len(o.data.vertices),
                "faces": len(o.data.polygons),
                "uv_layers": [uv.name for uv in o.data.uv_layers],
                "materials": [m.name if m else None
                              for m in o.data.materials],
                "weighted_verts": sum(
                    1 for v in o.data.vertices
                    if any(g.weight > 1e-6 for g in v.groups)),
            })
        if o.type == "ARMATURE":
            row.update({
                "bones": len(o.data.bones),
                "pose_bones": len(o.pose.bones),
                "animation_data": bool(o.animation_data),
            })
        objects.append(row)

    skins = [o for o in objects if o["type"] == "ARMATURE"]
    actions = [a.name for a in bpy.data.actions]
    images = [
        {"name": im.name, "size": list(im.size),
         "packed": bool(im.packed_file),
         "packed_bytes": int(im.packed_file.size) if im.packed_file else 0,
         "file_format": im.file_format}
        for im in bpy.data.images if im.source == "FILE"
    ]

    op = bpy.ops.export_scene.gltf
    props = sorted(p.identifier for p in op.get_rna_type().properties)
    wanted = ["export_format", "use_selection", "export_apply",
              "export_animations", "export_skins", "export_materials",
              "export_image_format", "export_texture_dir",
              "export_yup", "export_cameras", "export_lights",
              "export_extras", "export_gn_mesh", "use_visible",
              "use_renderable", "use_active_collection"]

    out = {
        "blender": bpy.app.version_string,
        "blend_sha256": hashlib.sha256(BLEND.read_bytes()).hexdigest(),
        "blend_bytes": BLEND.stat().st_size,
        "scene_frame": scene.frame_current,
        "engine": scene.render.engine,
        "objects": objects,
        "armature_count": len(skins),
        "action_count": len(actions),
        "actions": actions,
        "images": images,
        "gltf_export_poll": bool(op.poll()),
        "gltf_export_props_available": {k: k in props for k in wanted},
        "gltf_export_props_total": len(props),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    log("STRUCT " + json.dumps({
        "objects": [(o["name"], o["type"], o.get("verts"),
                     [m["type"] for m in o["modifiers"]]) for o in objects],
        "actions": actions, "images": len(images),
        "gltf_poll": out["gltf_export_poll"],
        "props_available": out["gltf_export_props_available"]},
        ensure_ascii=False))
    log("BLEND_STRUCTURE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
