"""Blender headless 探针：导入游戏真实 GLB，读回骨架/网格结构。

用法：
  blender.exe -b --factory-startup --python probe_glb_structure.py -- <glb> <out.json>
只写 out.json，不改任何工程文件。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    glb, out = Path(argv[0]), Path(argv[1])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    objs = []
    for o in bpy.data.objects:
        rec = {"name": o.name, "type": o.type,
               "parent": o.parent.name if o.parent else None,
               "matrix_world": [list(r) for r in o.matrix_world],
               "modifiers": [{"name": m.name, "type": m.type,
                              "object": getattr(getattr(m, "object", None),
                                               "name", None)}
                             for m in o.modifiers]}
        if o.type == "MESH":
            rec["vertices"] = len(o.data.vertices)
            rec["edges"] = len(o.data.edges)
            rec["polygons"] = len(o.data.polygons)
            rec["vertex_groups"] = [g.name for g in o.vertex_groups]
        if o.type == "ARMATURE":
            rec["bones"] = [
                {"name": b.name, "parent": b.parent.name if b.parent else None,
                 "head_local": list(b.head_local),
                 "tail_local": list(b.tail_local),
                 "matrix_local": [list(r) for r in b.matrix_local]}
                for b in o.data.bones]
        objs.append(rec)
    result = {"glb": str(glb), "glb_bytes": glb.stat().st_size,
              "blender": bpy.app.version_string,
              "objects": objs}
    out.write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n",
                   encoding="utf-8")
    print("PROBE_GLB_STRUCTURE_OK", len(objs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
