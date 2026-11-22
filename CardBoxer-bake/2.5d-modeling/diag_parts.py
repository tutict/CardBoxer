"""Object-level visual diagnosis: hide every mesh whose name contains a token.

  blender -b boxer_2d5.blend --python diag_parts.py -- arm
  blender -b boxer_2d5.blend --python diag_parts.py -- white_outer

Writes diag-<token>.png next to the .blend. Read-only with respect to the model.
"""

from __future__ import annotations

import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
token = args[0] if args else "NOTHING"
mode = args[1] if len(args) > 1 else "hide"

hidden = []
for ob in bpy.data.objects:
    if ob.type != "MESH":
        continue                      # keep camera and lights
    if mode == "only":
        ob.hide_render = token not in ob.name
    else:
        ob.hide_render = token != "NOTHING" and token in ob.name
    if ob.hide_render:
        hidden.append(ob.name)

scene = bpy.context.scene
scene.render.filepath = os.path.join(HERE, f"diag-{token}-{mode}.png")
bpy.ops.render.render(write_still=True)
print(f"DIAG_OK token={token} mode={mode} hidden={len(hidden)}", flush=True)
