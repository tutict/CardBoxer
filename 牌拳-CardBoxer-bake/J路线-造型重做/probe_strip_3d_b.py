"""按「侧视屏幕投影形状」精确反查那条细长飘带对应的壳 ID。

前两轮失败：
  * diag_strip_b.py 按 local z_span>0.5 扫非目标壳 → 0 个，
    但 b-after-side.png 里那条线跨了约 0.74 个屏幕高度；
    说明 local 坐标 / 对象变换 / 投影口径里有我没对齐的一环。
  * 隐藏所有非 MESH 对象后线仍在，且是「保留壳」灰色，
    排除 .blend 里其它对象干扰。

本探针不再猜 3D 坐标，直接用 world_to_camera_view 算每个壳在侧视相机
下的屏幕 bbox，按「纵向很长 + 横向很窄」这个**形状**筛，并渲隔离图确认。

只读 .blend；输出 data/strip_3d_b.json 与 shots/shell_isolate/b-strip-isolate.png。
用法：blender.exe -b --python probe_strip_3d_b.py
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

HERE = Path(__file__).resolve().parent
BLEND = HERE.parent / "A路线-资产重做" / "对手怪-可变形连续壳.blend"
TARGETS = HERE / "data" / "shell_targets_b.json"
OUT = HERE / "data" / "strip_3d_b.json"
SHOT = HERE / "shots" / "shell_isolate" / "b-strip-isolate.png"

Y_SPAN_MIN = 0.45
X_SPAN_MAX = 0.30
SIDE_VIEW = ((4.0, 0.0, 0.95), (math.pi / 2, 0.0, math.pi / 2))


def main() -> int:
    assert BLEND.is_file() and TARGETS.is_file()
    tg = json.loads(TARGETS.read_text(encoding="utf-8"))
    deleted = set(tg["target_shell_ids"])
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    scene = bpy.context.scene
    src = next(o for o in scene.objects
               if o.type == "MESH"
               and any(m.type == "SURFACE_DEFORM" for m in o.modifiers))
    mesh = src.data
    nv = len(mesh.vertices)
    parent = list(range(nv))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for p in mesh.polygons:
        vs = p.vertices
        for v in vs[1:]:
            union(vs[0], v)
    groups = defaultdict(list)
    for v in mesh.vertices:
        groups[find(v.index)].append(v.index)
    root_of = [find(v.index) for v in mesh.vertices]
    co0 = [tuple(v.co) for v in mesh.vertices]

    scene.render.resolution_x = 640
    scene.render.resolution_y = 768
    scene.render.resolution_percentage = 100
    cam_data = bpy.data.cameras.new("B_STRIP_CAM")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 2.1
    cam = bpy.data.objects.new("B_STRIP_CAM", cam_data)
    scene.collection.objects.link(cam)
    cam.location, cam.rotation_euler = SIDE_VIEW
    scene.camera = cam
    bpy.context.view_layer.update()

    mw = src.matrix_world
    # 主体在侧视图约占 x∈[0.29,0.55]；那条细线在 x>0.55。
    # 不假设它是一整个细长壳，直接找「有顶点落进线区域」的所有壳。
    roi_hits = []
    mw_points = {}
    rows = []
    for root, ids in groups.items():
        step = max(1, len(ids) // 40)
        sample = ids[::step][:40]
        pts = []
        for vi in sample:
            p = world_to_camera_view(scene, cam, mw @ Vector(co0[vi]))
            pts.append((p.x, p.y))
        mw_points[root] = pts
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        in_roi = [p for p in pts
                  if p[0] > 0.55 and 0.18 < p[1] < 0.98]
        if in_roi:
            roi_hits.append({
                "shell_id": root, "verts": len(ids),
                "already_deleted": root in deleted,
                "roi_points": len(in_roi), "sample_points": len(pts),
                "roi_x_range": [round(min(p[0] for p in in_roi), 4),
                                round(max(p[0] for p in in_roi), 4)],
                "roi_y_range": [round(min(p[1] for p in in_roi), 4),
                                round(max(p[1] for p in in_roi), 4)],
                "centroid": [round(
                    sum(co0[i][k] for i in ids) / len(ids), 4)
                    for k in range(3)],
            })
        xspan = max(xs) - min(xs)
        yspan = max(ys) - min(ys)
        if yspan >= Y_SPAN_MIN and xspan <= X_SPAN_MAX:
            rows.append({
                "shell_id": root, "verts": len(ids),
                "already_deleted": root in deleted,
                "screen_x_range": [round(min(xs), 4), round(max(xs), 4)],
                "screen_y_range": [round(min(ys), 4), round(max(ys), 4)],
                "screen_x_span": round(xspan, 4),
                "screen_y_span": round(yspan, 4),
                "local_z_span": round(
                    max(co0[i][2] for i in ids)
                    - min(co0[i][2] for i in ids), 4),
                "centroid": [round(
                    sum(co0[i][k] for i in ids) / len(ids), 4)
                    for k in range(3)],
            })
    rows.sort(key=lambda d: -d["screen_y_span"])

    # 渲隔离图：只留命中且未删的壳，其余顶点移出视锥。
    keep = ({r["shell_id"] for r in rows if not r["already_deleted"]}
            | {r["shell_id"] for r in roi_hits
               if not r["already_deleted"]})
    obj = src.copy()
    obj.data = src.data.copy()
    scene.collection.objects.link(obj)
    obj.name = "B_STRIP_ISO"
    for m in list(obj.modifiers):
        obj.modifiers.remove(m)
    obj.parent = None
    for o in scene.objects:
        if o is not obj and o.type not in ("CAMERA", "LIGHT", "EMPTY"):
            o.hide_render = True
    for v in obj.data.vertices:
        if root_of[v.index] in keep:
            v.co = co0[v.index]
        else:
            v.co = (co0[v.index][0], co0[v.index][1], -100.0)
    pm = obj.data
    pm.materials.clear()
    m = bpy.data.materials.new("B_STRIP_ONLY")
    m.diffuse_color = (0.95, 0.15, 0.75, 1.0)
    pm.materials.append(m)
    for p in pm.polygons:
        p.material_index = 0
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "FLAT"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = False
    scene.render.film_transparent = True
    scene.render.filepath = str(SHOT)
    bpy.ops.render.render(write_still=True)

    # 订正：第一版把「没找到未删的细长壳」判成 FAIL，但那其实是
    # 正确结论（两片披风都已被删）。改为守事实，不再要求「必须有漏网」。
    checks = {
        "shells_2809": len(groups) == 2809,
        "long_narrow_candidates_found": len(rows) > 0,
        "all_long_narrow_shells_already_deleted": all(
            r["already_deleted"] for r in rows),
        "roi_hits_found": len(roi_hits) > 0,
        "shot_written": SHOT.is_file() and SHOT.stat().st_size > 2000,
    }
    report = {
        "source_blend": str(BLEND),
        "object_matrix_world": [list(r) for r in mw],
        "camera": {"location": list(SIDE_VIEW[0]),
                   "rotation": list(SIDE_VIEW[1]),
                   "ortho_scale": 2.1},
        "rule": {"screen_y_span_min": Y_SPAN_MIN,
                 "screen_x_span_max": X_SPAN_MAX,
                 "note": "按侧视屏幕形状，不用 local z_span"},
        "candidates": rows, "candidate_count": len(rows),
        "roi_hits": roi_hits, "roi_hit_count": len(roi_hits),
        "roi_undeleted_ids": sorted(
            r["shell_id"] for r in roi_hits
            if not r["already_deleted"]),
        "undeleted_ids": sorted(keep),
        "shot": str(SHOT),
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
    }
    report["ok"] = not report["failed"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("MATRIX_WORLD", [[round(v, 4) for v in r] for r in mw])
    print("CANDIDATES", len(rows), "UNDELETED", len(keep))
    for d in rows[:20]:
        print("STRIP", d["shell_id"], "verts", d["verts"],
              "deleted", d["already_deleted"],
              "yspan", d["screen_y_span"], "xspan", d["screen_x_span"],
              "local_z_span", d["local_z_span"])
    for k, v in checks.items():
        print("CHECK", k, v)
    print("STRIP_3D_B_OK" if report["ok"] else "STRIP_3D_B_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
