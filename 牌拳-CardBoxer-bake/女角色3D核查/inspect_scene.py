"""只读核查：打开 E 路线交付的 .blend，记录「打开即所见」到底是谁。

不修改、不回写任何既有 .blend；渲染输出全部落在女角色3D核查/。
两张图：
  A 原样（不改任何 hide_render）——用户双击打开后按 F12 看到的东西；
  B 隐藏 Voxel 代理壳 —— E 路线代表帧/交付板实际使用的口径。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import bpy

HERE = Path(__file__).resolve().parent
BLEND = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer-bake\E路线-玩家3D绑骨\玩家V4b-可变形连续壳.blend")
OUT = HERE / "scene_inventory.json"

bpy.ops.wm.open_mainfile(filepath=str(BLEND))
scene = bpy.context.scene


def obj_row(o):
    mats = [m.name if m else None for m in o.data.materials] if o.type == "MESH" else []
    return {
        "name": o.name,
        "type": o.type,
        "hide_render": bool(o.hide_render),
        "hide_viewport": bool(o.hide_viewport),
        "hide_get": bool(o.hide_get()),
        "dimensions": [round(v, 4) for v in o.dimensions],
        "location": [round(v, 4) for v in o.location],
        "verts": len(o.data.vertices) if o.type == "MESH" else None,
        "materials": mats,
        "modifiers": [
            {"name": m.name, "type": m.type,
             "target": m.target.name if m.type == "SURFACE_DEFORM" and m.target else None,
             "is_bound": bool(getattr(m, "is_bound", False)) if m.type == "SURFACE_DEFORM" else None}
            for m in o.modifiers],
    }


objects = [obj_row(o) for o in scene.objects]
images = [{"name": im.name, "size": list(im.size),
           "packed": im.packed_file is not None}
          for im in bpy.data.images]
info = {
    "blend": str(BLEND),
    "blend_bytes": BLEND.stat().st_size,
    "objects": objects,
    "images": images,
    "camera": scene.camera.name if scene.camera else None,
    "engine": scene.render.engine,
    "resolution": [scene.render.resolution_x, scene.render.resolution_y,
                   scene.render.resolution_percentage],
    "world": scene.world.name if scene.world else None,
}
print("SCENE_OBJECTS", json.dumps(objects, ensure_ascii=False))
print("IMAGES", json.dumps(images, ensure_ascii=False))
print("CAMERA", info["camera"], "ENGINE", info["engine"],
      "RES", info["resolution"])

scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = True

# A：打开即所见，一个 hide 都不动
scene.render.filepath = str(HERE / "A-打开即所见.png")
bpy.ops.render.render(write_still=True)
print("RENDER_A_OK", (HERE / "A-打开即所见.png").stat().st_size)

# B：隐藏代理壳，交付板用的口径
shell = next((o for o in scene.objects
              if o.type == "MESH" and o.name == "e_continuous_shell"), None)
hi = next((o for o in scene.objects
           if o.type == "MESH"
           and any(m.type == "SURFACE_DEFORM" for m in o.modifiers)), None)
if shell is not None:
    shell.hide_render = True
if hi is not None:
    hi.hide_render = False
scene.render.filepath = str(HERE / "B-隐藏代理壳.png")
bpy.ops.render.render(write_still=True)
print("RENDER_B_OK", (HERE / "B-隐藏代理壳.png").stat().st_size,
      "shell_hidden", shell is not None)

info["renders"] = ["A-打开即所见.png", "B-隐藏代理壳.png"]
OUT.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n",
               encoding="utf-8")
print("SCENE_INSPECT_OK")
