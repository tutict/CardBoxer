"""Single-variable probe for the disappearing torso.

Renders three images of the jab pose and prints the material/geometry facts:
  1. only the white_outer BODY mesh (exact name)
  2. only the white_outer_outline mesh (exact name)
  3. only the BODY with all three ramp bands forced to pure RED

If (3) is still blank, the body mesh is not being drawn at all (geometry /
bevel / winding), not a colour-vs-background problem.
"""

from __future__ import annotations

import json
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import boxer_2d5 as B  # noqa: E402

with open(B.TABLE, "r", encoding="utf-8") as handle:
    table = json.load(handle)

model = B.Model()
scene = B.setup_scene(0.0)
model.pose(B.joints_of(table, "jab", 7))

for name in ("white_outer", "white_outer_outline"):
    ob = bpy.data.objects[name]
    mesh = ob.data
    zs = [v.co.z for v in mesh.vertices]
    xs = [v.co.x for v in mesh.vertices]
    mats = [m.name for m in mesh.materials]
    print(f"GEOM {name}: verts={len(mesh.vertices)} polys={len(mesh.polygons)} "
          f"x=({min(xs):.3f},{max(xs):.3f}) z=({min(zs):.3f},{max(zs):.3f}) "
          f"mats={mats}", flush=True)

body = bpy.data.objects["white_outer"]
ramp = next(n for n in body.data.materials[0].node_tree.nodes if n.type == "VALTORGB")
print("BANDS " + ", ".join(
    f"pos={e.position:.2f} rgb=({e.color[0]:.2f},{e.color[1]:.2f},{e.color[2]:.2f})"
    for e in ramp.color_ramp.elements), flush=True)


def render_only(exact_name: str, out_name: str) -> None:
    for ob in bpy.data.objects:
        if ob.type == "MESH":
            ob.hide_render = ob.name != exact_name
    scene.render.filepath = os.path.join(HERE, out_name)
    bpy.ops.render.render(write_still=True)
    print(f"DIAGBODY_OK {out_name}", flush=True)


render_only("white_outer", "diag-body-only.png")
render_only("white_outer_outline", "diag-outline-only.png")

for el in ramp.color_ramp.elements:
    el.color = (1.0, 0.05, 0.05, 1.0)
render_only("white_outer", "diag-body-red.png")
