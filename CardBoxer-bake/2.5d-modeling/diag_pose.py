"""Object-level diagnosis for ANY frame, not just the saved rest pose.

  blender -b --factory-startup --python diag_pose.py -- jab 7 arm only
  blender -b --factory-startup --python diag_pose.py -- jab 7 leg only
  blender -b --factory-startup --python diag_pose.py -- jab 7 white_outer only

Rebuilds the model, poses it from baked2.json, then hides/shows meshes by name.
"""

from __future__ import annotations

import json
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import boxer_2d5 as B  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
card = None if not args or args[0] == "stance" else args[0]
frame = int(args[1]) if len(args) > 1 else 0
token = args[2] if len(args) > 2 else "NOTHING"
mode = args[3] if len(args) > 3 else "hide"

with open(B.TABLE, "r", encoding="utf-8") as handle:
    table = json.load(handle)

model = B.Model()
scene = B.setup_scene(0.0)
model.pose(B.joints_of(table, card, frame))
model.set_palette(B.PLAYER_GLOVE)

hidden = []
for ob in bpy.data.objects:
    if ob.type != "MESH":
        continue
    if mode == "only":
        ob.hide_render = token not in ob.name
    else:
        ob.hide_render = token != "NOTHING" and token in ob.name
    if ob.hide_render:
        hidden.append(ob.name)

label = card or "stance"
scene.render.filepath = os.path.join(HERE, f"diagpose-{label}{frame}-{token}-{mode}.png")
bpy.ops.render.render(write_still=True)
print(f"DIAGPOSE_OK {label} f{frame} token={token} mode={mode} hidden={len(hidden)}", flush=True)
