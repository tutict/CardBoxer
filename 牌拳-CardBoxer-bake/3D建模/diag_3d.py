"""Numeric isolation for the v2 "floating grey rectangles" bug.

Two questions, both measured rather than guessed:

  1. Does boxer_rig.place() land every BONE where baked2.json says, on both a
     rest frame and a stretched (jab impact) frame?
  2. Does the SKINNED MESH land on that bone, or does the ARMATURE modifier's
     parent-chain deformation fling it elsewhere? (v2's contact sheet showed
     orphaned rectangles only on motion frames, never on stance.)

An ORPHAN is a skinned mesh whose bbox centre is >20 game px from its bone's
midpoint -- that cannot be explained by a limb radius of 7..13 px.
"""
from __future__ import annotations

import json
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import boxer_3d as B  # noqa: E402
import boxer_rig  # noqa: E402

with open(B.TABLE, "r", encoding="utf-8") as handle:
    table = json.load(handle)


def expected_chain(j):
    hip, sh, hd = j["hip"], j["shoulder"], j["head"]
    A = hip
    Bp = B.lerp(hip, sh, 0.26)
    C = B.lerp(hip, sh, 0.60)
    D = sh
    E = B.lerp(sh, hd, 0.58)
    F = hd
    return {
        "hips": (A, Bp), "spine": (Bp, C), "chest": (C, D), "neck": (D, E), "head": (E, F),
        "upperarm_f": (sh, j["f_elbow"]), "forearm_f": (j["f_elbow"], j["f_hand"]),
        "upperarm_b": (sh, j["b_elbow"]), "forearm_b": (j["b_elbow"], j["b_hand"]),
        "thigh_f": (B.offset(hip, 4.0, 0.0), j["f_knee"]), "shin_f": (j["f_knee"], j["f_foot"]),
        "thigh_b": (B.offset(hip, -4.0, 0.0), j["b_knee"]), "shin_b": (j["b_knee"], j["b_foot"]),
    }


def run_case(model, scene, cam, label, card, frame):
    j = B.joints_of(table, card, frame)
    model.pose(j)
    bpy.context.view_layer.update()
    expected = expected_chain(j)

    print(f"=== {label}: bone pose readback (game px) ===", flush=True)
    worst = 0.0
    for name, (eh, et) in expected.items():
        pb = model.arm.pose.bones[name]
        gh, gt = boxer_rig.pt(pb.head), boxer_rig.pt(pb.tail)
        dh, dt = math.dist(gh, eh), math.dist(gt, et)
        worst = max(worst, dh, dt)
        flag = "OK" if max(dh, dt) < 2.0 else "OFF"
        print(f"BONE {label} {name:12s} {flag:3s} d_head={dh:.1f} d_tail={dt:.1f} "
              f"scale_y={pb.scale.y:.3f}", flush=True)
    print(f"WORST_BONE_ERROR {label} {worst:.2f}", flush=True)

    print(f"=== {label}: skinned mesh centre vs bone midpoint ===", flush=True)
    dg = bpy.context.evaluated_depsgraph_get()
    orphans = []
    for name, ob in model.skinned.items():
        ev = ob.evaluated_get(dg)
        mesh = ev.to_mesh()
        pts = [ev.matrix_world @ v.co for v in mesh.vertices]
        cx = sum(p.x for p in pts) / len(pts) * 100.0
        cy = sum(-p.z for p in pts) / len(pts) * 100.0
        ys = [p.y * 100 for p in pts]
        ev.to_mesh_clear()
        eh, et = expected[name]
        mx, my = (eh[0] + et[0]) / 2.0, (eh[1] + et[1]) / 2.0
        dist = math.dist((cx, cy), (mx, my))
        if dist > 20.0:
            orphans.append((name, round(dist, 1)))
        print(f"MESH {label} {name:12s} centre=({cx:7.1f},{cy:7.1f}) "
              f"bone_mid=({mx:7.1f},{my:7.1f}) d={dist:6.1f} "
              f"depth=[{min(ys):6.1f},{max(ys):6.1f}] "
              f"{'ORPHAN' if dist > 20.0 else 'ok'}", flush=True)
    print(f"ORPHANS {label} {orphans}", flush=True)

    for view, show_skinned, show_props in (("all", True, True), ("skin_only", True, False)):
        for ob in model.skinned.values():
            ob.hide_render = not show_skinned
        for ob in model.props.values():
            ob.hide_render = not show_props
        for ob in bpy.data.objects:
            if ob.type == "EMPTY":
                ob.hide_render = True
        path = os.path.join(HERE, f"diag3d-{label}-{view}.png")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        print(f"DIAG_OK {label} {view}", flush=True)
    return orphans


def main() -> int:
    model = B.Model()
    scene, cam = B.setup_scene()
    B.set_camera(cam, 0.0)
    results = {}
    for label, card, frame in (("stance", None, 0), ("jab", "jab", 7), ("sweep", "sweep", 13)):
        results[label] = run_case(model, scene, cam, label, card, frame)
    print("DIAG_SUMMARY " + json.dumps({k: v for k, v in results.items()}), flush=True)
    print("DIAG_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
