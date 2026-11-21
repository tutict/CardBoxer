"""用游戏自己的逐帧关节表驱动「新 3D 建模人物」的 13 骨，渲攻击帧序列。

坐标桥与《牌拳》既有管线完全一致：
    baked2.json 的 11 关节是 game px（脚下原点，+x 前，-y 上）；
    boxer_rig.BONES 的 rest 骨架在 Blender 里是 (x, 0, -game_y/100)。
    本脚本把每根 pose bone 直接摆到 (head -> tail) 的旋转矩阵上。

与 boxer_rig.place() 的关键差别：这里**不写 pb.scale**。
    place() 需要拉伸骨骼来复现游戏里被拉伸的四肢（jab 前臂 2.5x），
    那对「按骨段拼出来的程序化几何」是对的；
    但 AI 生成的模型是一整张连续人形网格、按最近骨骼段刚性赋权，
    再沿骨轴缩放只会把薄壳撕成橡皮。所以只旋转、不缩放，
    每段网格做刚体变换，把撕裂压到最小。

本脚本只读 .blend、只往 3D攻击GIF/ 写 PNG 与 manifest；
不回写任何既有归档，不碰游戏源码，不渲进 Godot。

用法：
  blender -b --python render_3d_frames.py -- --tag foe --probe
  blender -b --python render_3d_frames.py -- --tag foe --cards jab,cross,wave
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
sys.path.insert(0, str(BAKE))
import boxer_rig  # noqa: E402 -- BONES 是骨骼名单的唯一来源

TABLE = BAKE / "baked2.json"
JOINTS = ("hip", "shoulder", "head", "f_elbow", "f_hand", "b_elbow",
          "b_hand", "f_knee", "f_foot", "b_knee", "b_foot")
CARDS = ("jab", "cross", "wave")


def log(*a):
    print(*a, flush=True)


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def chain_of(j: dict):
    """13 根骨的 (name, head_game_px, tail_game_px)，拓扑顺序（父在子前）。

    躯干四段按 boxer_3d.py:445 的插值拆法，四肢按 11 关节直连；
    头骨单独跟在 neck 之后，保持纯旋转不缩放。
    """
    hip, sh, hd = j["hip"], j["shoulder"], j["head"]
    A = hip
    B = lerp(hip, sh, 0.26)
    C = lerp(hip, sh, 0.60)
    D = sh
    E = lerp(sh, hd, 0.58)
    F = hd
    return [
        ("hips", A, B),
        ("spine", B, C),
        ("chest", C, D),
        ("neck", D, E),
        ("head", E, F),
        ("upperarm_f", sh, j["f_elbow"]),
        ("forearm_f", j["f_elbow"], j["f_hand"]),
        ("upperarm_b", sh, j["b_elbow"]),
        ("forearm_b", j["b_elbow"], j["b_hand"]),
        ("thigh_f", (hip[0] + 4.0, hip[1]), j["f_knee"]),
        ("shin_f", j["f_knee"], j["f_foot"]),
        ("thigh_b", (hip[0] - 4.0, hip[1]), j["b_knee"]),
        ("shin_b", j["b_knee"], j["b_foot"]),
    ]


def pose_rigid(arm, j: dict) -> None:
    for name, h, t in chain_of(j):
        dx = (t[0] - h[0]) / 100.0
        dz = -(t[1] - h[1]) / 100.0
        u = Vector((dx, 0.0, dz))
        if u.length < 1e-8:
            continue
        u.normalize()
        mat = u.to_track_quat("Y", "Z").to_matrix().to_4x4()
        mat.translation = Vector((h[0] / 100.0, 0.0, -h[1] / 100.0))
        arm.pose.bones[name].matrix = mat
        bpy.context.view_layer.update()


def joints_of(table: dict, card: str | None, frame: int) -> dict:
    if card is None:
        return {k: tuple(v) for k, v in table["stance"].items()}
    tracks = table["cards"] if card in table["cards"] else table["motions"]
    return {k: tuple(tracks[card]["track"][frame][k]) for k in JOINTS}


def joint_sha(j: dict) -> str:
    payload = json.dumps({k: list(v) for k, v in sorted(j.items())}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def evaluated_positions(meshes):
    dg = bpy.context.evaluated_depsgraph_get()
    out = []
    for o in meshes:
        ev = o.evaluated_get(dg)
        m = ev.to_mesh()
        out.extend([(ev.matrix_world @ v.co).copy() for v in m.vertices])
        ev.to_mesh_clear()
    return out


def setup_camera(scene, angle_deg, res):
    cam = next((o for o in scene.objects if o.type == "CAMERA"), None)
    assert cam is not None, "blend has no camera"
    a = math.radians(angle_deg)
    R, tz = 4.0, 0.86
    cam.location = (R * math.sin(a), -R * math.cos(a), tz)
    cam.rotation_euler = (Vector((0.0, 0.0, tz)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 2.30
    scene.camera = cam
    scene.render.resolution_x = res
    scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    return cam


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", default=str(BAKE / "对手怪Blender建模V1" / "对手怪V1.blend"))
    ap.add_argument("--tag", default="foe")
    ap.add_argument("--cards", default=",".join(CARDS))
    ap.add_argument("--res", type=int, default=512)
    ap.add_argument("--angle", type=float, default=0.0)
    ap.add_argument("--probe", action="store_true")
    args = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])

    blend = Path(args.blend)
    assert blend.is_file(), f"missing blend: {blend}"
    table = json.loads(TABLE.read_text(encoding="utf-8"))

    t0 = time.time()
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    scene = bpy.context.scene
    meshes = [o for o in scene.objects if o.type == "MESH"]
    arm = next((o for o in scene.objects if o.type == "ARMATURE"), None)
    assert meshes and arm, "blend is missing mesh or armature"
    bone_names = [b[0] for b in boxer_rig.BONES]
    assert sorted(arm.pose.bones.keys()) == sorted(bone_names), "bone set mismatch"
    for pb in arm.pose.bones:
        pb.bone.inherit_scale = "NONE"  # 纯旋转驱动，不让父级 scale 渗进子骨
    verts = sum(len(o.data.vertices) for o in meshes)
    tris = sum(len(o.data.polygons) for o in meshes)
    modifiers = [(o.name, m.type) for o in meshes for m in o.modifiers
                 if m.type == "ARMATURE"]
    assert modifiers, "no ARMATURE modifier on any mesh"
    log(f"OPEN {blend.name} meshes={len(meshes)} verts={verts} tris={tris} "
        f"bones={len(arm.pose.bones)} arm_modifiers={len(modifiers)}")

    setup_camera(scene, args.angle, args.res)
    outdir = HERE / "frames" / args.tag
    outdir.mkdir(parents=True, exist_ok=True)

    if args.probe:
        shots = [("stance", None, 0), ("jab", "jab", 7), ("wave", "wave", 18)]
    else:
        shots = []
        for cid in args.cards.split(","):
            cid = cid.strip()
            n = int(table["cards"][cid]["frames"])
            shots.extend((cid, cid, f) for f in range(n))
        shots.insert(0, ("stance", None, 0))

    # 变形承重证据：站架 vs 刺拳命中，逐顶点最大位移（证明真的驱动了网格）
    pose_rigid(arm, joints_of(table, None, 0))
    rest_pos = evaluated_positions(meshes)
    pose_rigid(arm, joints_of(table, "jab", 7))
    posed_pos = evaluated_positions(meshes)
    assert len(rest_pos) == len(posed_pos) == verts
    deltas = [(a - b).length for a, b in zip(rest_pos, posed_pos)]
    deform = {
        "vertices": verts,
        "moved_gt_1mm": sum(1 for d in deltas if d > 1e-3),
        "max_displacement_m": round(max(deltas), 5),
        "mean_displacement_m": round(sum(deltas) / len(deltas), 5),
        "a": "stance", "b": "jab frame 7 (index 0-based)",
        "driver": "pose bone matrix, rotation only, scale=1",
    }
    log(f"DEFORM {json.dumps(deform, ensure_ascii=False)}")

    manifest = []
    for label, card, frame in shots:
        j = joints_of(table, card, frame)
        pose_rigid(arm, j)
        phase = "stance" if card is None else table["cards"][card]["track"][frame]["phase"]
        path = outdir / f"{label}_f{frame:03d}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        png = path.read_bytes()
        assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 10000, f"bad png {path.name}"
        manifest.append({
            "file": path.name, "label": label, "card": card, "frame": frame,
            "phase": phase, "joints_sha256": joint_sha(j),
            "png_sha256": hashlib.sha256(png).hexdigest(), "bytes": len(png),
        })
        log(f"FRAME {path.name} card={card} f={frame} phase={phase} bytes={len(png)}")

    report = {
        "blend": str(blend.relative_to(BAKE)).replace("\\", "/"),
        "blend_sha256": hashlib.sha256(blend.read_bytes()).hexdigest(),
        "table": "baked2.json",
        "table_sha256": hashlib.sha256(TABLE.read_bytes()).hexdigest(),
        "tag": args.tag,
        "blender": bpy.app.version_string,
        "mesh": {"objects": len(meshes), "verts": verts, "tris": tris,
                 "armature_modifiers": modifiers},
        "bones": sorted(arm.pose.bones.keys()),
        "driver": "chain_of(joints) -> pb.matrix, rotation only (no pb.scale)",
        "camera": {"type": "ORTHO", "angle_deg": args.angle,
                   "ortho_scale": 2.30, "target_z": 0.86, "res": args.res,
                   "film_transparent": True},
        "deform_probe": deform,
        "frames": manifest,
        "elapsed_seconds": round(time.time() - t0, 2),
    }
    (outdir / "manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"RENDER_3D_OK tag={args.tag} frames={len(manifest)} "
        f"elapsed={report['elapsed_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
