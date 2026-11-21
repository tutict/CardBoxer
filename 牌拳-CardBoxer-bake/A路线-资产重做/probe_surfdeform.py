"""A 路线探针 A2：连续壳当变形骨架，原高模用 Surface Deform 跟随。

思路：C 路线把权重「回传」给 2,809 个开放薄壳，每个碎片各走各的，
所以关节处容易撕。改成让 Voxel 连续壳（3 壳）自己挂 13 骨平滑变形，
原高模通过 SURFACE_DEFORM 修改器跟随连续表面 —— UV / 3 张 PBR
一张不动，碎片被连续面带着走。

只读源 .blend；产物全写本工作区。不回写 V2 / C 路线归档。
用法：blender.exe -b --python probe_surfdeform.py
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # 别在已归档的 V2 目录里刷新 __pycache__

import hashlib
import json
import time
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
sys.path.insert(0, str(BAKE / "C路线-变形质量V2"))
sys.path.insert(0, str(BAKE / "C路线-真3D修复"))
import c2_build as C2  # noqa: E402
import c_build as C  # noqa: E402

BLEND = BAKE / "对手怪Blender建模V1" / "对手怪V1.blend"
TABLE = BAKE / "baked2.json"
SPEC = BAKE / "3D攻击GIF" / "apose_joints.json"
MAPPING = BAKE / "3D攻击GIF" / "puppet_mapping.json"
VOXEL = 0.020


def log(*a):
    print(*a, flush=True)


def shell_count(mesh):
    n = len(mesh.vertices)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in mesh.edges:
        a, b = find(e.vertices[0]), find(e.vertices[1])
        if a != b:
            parent[b] = a
    return len({find(i) for i in range(n)})


def main() -> int:
    t0 = time.time()
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    stance = C.joints_of(table, None, 0)
    P = C.apose_points(spec)

    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    scene = bpy.context.scene
    src = next(o for o in scene.objects if o.type == "MESH")
    for o in list(scene.objects):
        if o.type == "ARMATURE":
            bpy.data.objects.remove(o, do_unlink=True)
    # 原高模自带的 ARMATURE 修改器必须去掉，否则会和 Surface Deform 叠两次
    for m in list(src.modifiers):
        src.modifiers.remove(m)
    src.hide_render = False
    src_shells = shell_count(src.data)
    src_uv = len(src.data.uv_layers)
    src_tex = C.texture_inventory(src)
    log(f"SRC verts={len(src.data.vertices)} shells={src_shells} "
        f"uv={src_uv} tex={len(src_tex)}")

    # --- 1. A-pose rest 13 骨（与 C 路线同公式）-----------------------------
    arm_data = bpy.data.armatures.new("a_apose_rig")
    rig = bpy.data.objects.new("a_apose_rig", arm_data)
    scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    made = {}
    for name, parent, u, v in C.CHAIN:
        eb = arm_data.edit_bones.new(name)
        hx, hz = P[u]
        tx, tz = P[v]
        eb.head, eb.tail = (hx, 0.0, hz), (tx, 0.0, tz)
        if parent:
            eb.parent = made[parent]
        made[name] = eb
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in rig.pose.bones:
        pb.bone.inherit_scale = "NONE"
    bpy.context.view_layer.update()

    # --- 2. Voxel 连续壳 + 自动权重 ------------------------------------------
    shell = C.fresh_copy(src, "a_continuous_shell")
    shell.data.remesh_voxel_size = VOXEL
    shell.data.remesh_voxel_adaptivity = 0.0
    bpy.ops.object.select_all(action="DESELECT")
    shell.select_set(True)
    bpy.context.view_layer.objects.active = shell
    assert bpy.ops.object.voxel_remesh.poll()
    bpy.ops.object.voxel_remesh()
    # Surface Deform 要求 target 全是凸多边形；Voxel Remesh 的 quad 常不共面，
    # 实测 bind 时警告 "Target contains concave polygons" 且 is_bound=False。
    # 三角化只改面不改顶点，vertex group 权重不受影响。
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(shell.data)
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bm.to_mesh(shell.data)
    bm.free()
    shell.data.update()
    shell_v = len(shell.data.vertices)
    shell_shells = shell_count(shell.data)
    C.auto_weight(shell, rig)
    shell_covered = sum(1 for v in shell.data.vertices
                        if any(g.weight > 1e-6 for g in v.groups))
    log(f"SHELL verts={shell_v} shells={shell_shells} "
        f"auto_weight={shell_covered}/{shell_v}")

    # --- 3. 原高模改成 Surface Deform 跟随 -----------------------------------
    bpy.ops.object.select_all(action="DESELECT")
    src.select_set(True)
    bpy.context.view_layer.objects.active = src
    sd = src.modifiers.new("follow_continuous_shell", "SURFACE_DEFORM")
    sd.target = shell
    bind_poll = bool(bpy.ops.object.surfacedeform_bind.poll())
    bind_err = None
    if bind_poll:
        try:
            bpy.ops.object.surfacedeform_bind(modifier=sd.name)
        except Exception as exc:
            bind_err = f"{type(exc).__name__}: {exc}"
    bound = bool(getattr(sd, "is_bound", False))
    log(f"BIND poll={bind_poll} is_bound={bound} err={bind_err}")
    if not bound:
        report = {"bind_poll": bind_poll, "is_bound": False,
                  "bind_error": bind_err, "verdict": "SURFACE_DEFORM_BIND_FAILED"}
        (HERE / "surfdeform_probe.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        log("SURFACE_DEFORM_BIND_FAILED")
        return 1

    # --- 4. 量化：静止漂移 / 驱动位移 / 边撕裂 -------------------------------
    C.setup_camera(scene, 0.0)
    rest_pos, rest_edges = C.evaluated(src)
    raw = [src.matrix_world @ v.co for v in src.data.vertices]
    bind_drift = max((a - b).length for a, b in zip(rest_pos, raw))
    hf, hb, foot = C2.clusters(rest_pos, P)
    hip_z, sh_z = P["hip"][1], P["shoulder"][1]

    def render(name, deg=0.0):
        C.setup_camera(scene, deg)
        src.hide_render = False
        shell.hide_render = True
        path = HERE / "frames" / f"{name}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        b = path.read_bytes()
        assert b[:8] == b"\x89PNG\r\n\x1a\n" and len(b) > 10000
        return {"file": path.name, "bytes": len(b),
                "sha256": hashlib.sha256(b).hexdigest()}

    rest_png = render("a2-rest")

    frames = []
    for cid, fr in (("jab", 6), ("cross", 10), ("wave", 17)):
        d, r, sig = C.pose_frame(rig, P, table, stance, cid, fr, mapping)
        pos, _ = C.evaluated(src)
        m = C2.frame_metrics(rest_pos, rest_edges, pos, hf, hb, foot, hip_z, sh_z)
        png = render(f"a2-{cid}{fr:02d}")
        frames.append({"card": cid, "frame": fr,
                       "max_delta_deg": sig["mapped_max_abs_deg"],
                       "metrics": m, "png": png})
        log(f"FRAME {cid}{fr:02d} {json.dumps(m)}")

    side_png = render("a2-stance-angle55", 55.0)
    after = {"uv_layers": len(src.data.uv_layers),
             "materials": len(src.data.materials),
             "textures": C.texture_inventory(src),
             "uv_same": len(src.data.uv_layers) == src_uv,
             "textures_same": C.texture_inventory(src) == src_tex}

    report = {
        "blend_sha256": hashlib.sha256(BLEND.read_bytes()).hexdigest(),
        "blender": bpy.app.version_string,
        "method": "Voxel continuous shell + ARMATURE_AUTO, original high-poly "
                  "follows via SURFACE_DEFORM (UV/PBR untouched)",
        "voxel_size": VOXEL,
        "src": {"verts": len(src.data.vertices), "shells": src_shells,
                "uv": src_uv, "textures": len(src_tex)},
        "shell": {"verts": shell_v, "shells": shell_shells,
                  "auto_weight_covered": shell_covered},
        "bind": {"poll": bind_poll, "is_bound": bound, "error": bind_err,
                 "rest_drift_m": round(bind_drift, 8)},
        "assets_after": after,
        "frames": frames,
        "rest_png": rest_png, "side_png": side_png,
        "elapsed_seconds": round(time.time() - t0, 2),
    }
    (HERE / "surfdeform_probe.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    log(f"ASSETS {json.dumps(after, ensure_ascii=False)}")
    log(f"SURFACE_DEFORM_PROBE_OK elapsed={report['elapsed_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
