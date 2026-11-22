"""诊断 .blend 里 2,809 个连通壳的形状，判断腰间斜片/下摆锯齿是不是游离小壳。

C 路线验证记录写明「没修生成模型自带的 2,809 壳与腰间游离碎片」。
本探针回答：碎片能不能按连通分量安全剔除，而不误删配件/贴图。

只读源 .blend；产物全部写进本工作区。
用法：blender.exe -b --python probe_shells.py
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import bmesh
import bpy

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
BLEND = BAKE / "foe-blender-modeling-v1" / "foe-V1.blend"


def log(*a):
    print(*a, flush=True)


def main() -> int:
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    scene = bpy.context.scene
    src = next(o for o in scene.objects if o.type == "MESH")
    mesh = src.data
    n = len(mesh.vertices)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for e in mesh.edges:
        union(e.vertices[0], e.vertices[1])
    comps = {}
    for i in range(n):
        comps.setdefault(find(i), []).append(i)
    comp_list = sorted(comps.values(), key=len, reverse=True)

    sizes = [len(c) for c in comp_list]
    buckets = Counter()
    for s in sizes:
        if s < 10:
            buckets["<10"] += 1
        elif s < 50:
            buckets["10-49"] += 1
        elif s < 200:
            buckets["50-199"] += 1
        elif s < 1000:
            buckets["200-999"] += 1
        elif s < 5000:
            buckets["1000-4999"] += 1
        else:
            buckets[">=5000"] += 1

    def bbox(idx):
        xs = [mesh.vertices[i].co.x for i in idx]
        ys = [mesh.vertices[i].co.y for i in idx]
        zs = [mesh.vertices[i].co.z for i in idx]
        return [[round(min(xs), 4), round(min(ys), 4), round(min(zs), 4)],
                [round(max(xs), 4), round(max(ys), 4), round(max(zs), 4)]]

    top = [{"rank": k + 1, "verts": len(c), "bbox": bbox(c)}
           for k, c in enumerate(comp_list[:12])]
    small = [c for c in comp_list if len(c) < 200]
    small_verts = sum(len(c) for c in small)
    log(f"SHELLS total={len(comp_list)} verts={n} buckets={dict(buckets)}")
    log(f"SMALL(<200) shells={len(small)} verts={small_verts} "
        f"pct={small_verts/n:.4f}")
    for t in top:
        log(f"TOP {json.dumps(t)}")

    # 只留小壳渲一张，肉眼确认这些是不是腰间斜片 / 下摆锯齿
    keep = set(i for c in small for i in c)
    tmp = src.copy()
    tmp.data = mesh.copy()
    scene.collection.objects.link(tmp)
    tmp.name = "shells_small_only"
    bm = bmesh.new()
    bm.from_mesh(tmp.data)
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    for v in list(bm.verts):
        if v.index not in keep:
            bm.verts.remove(v)
    bm.to_mesh(tmp.data)
    bm.free()
    tmp.data.update()
    src.hide_render = True
    tmp.hide_render = False
    cam = next(o for o in scene.objects if o.type == "CAMERA")
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 2.30
    scene.camera = cam
    scene.render.resolution_x = scene.render.resolution_y = 768
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True
    path = HERE / "frames" / "shells-small-only.png"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    png = path.read_bytes()
    log(f"SMALL_ONLY_PNG bytes={len(png)}")

    out = {
        "blend_sha256": hashlib.sha256(BLEND.read_bytes()).hexdigest(),
        "verts": n, "shells": len(comp_list), "buckets": dict(buckets),
        "top": top,
        "small": {"threshold": 200, "shells": len(small),
                  "verts": small_verts, "vert_pct": round(small_verts / n, 5),
                  "largest": max((len(c) for c in small), default=0)},
        "small_only_png": {"file": path.name, "bytes": len(png),
                           "sha256": hashlib.sha256(png).hexdigest()},
        "largest_shell_verts": sizes[0],
        "top5_vert_coverage": round(sum(sizes[:5]) / n, 5),
    }
    (HERE / "shells_probe.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log("SHELLS_PROBE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
