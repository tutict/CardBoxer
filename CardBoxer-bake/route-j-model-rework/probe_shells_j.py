"""J 路线 P1：壳级剪影手术可行性探针（Blender 5.2.3 headless）。

只读 A 路线 .blend，按面连通把 2,809 个壳分组，算每壳空间位置，
判断能否按「区域规则」精确筛出 V4b 同源部件（头冠 / 披风 / 长衫下摆）。
并渲一张按区域上色的分类图，让规则可被看图证伪。

用法：
  blender.exe -b --python probe_shells_j.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
import bpy

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
BLEND = BAKE / "route-a-asset-rework" / "foe-deformable-continuous-shell.blend"
OUT = HERE / "data" / "shells_j.json"
BOARD = HERE / "boards" / "J-shell-color-classification.png"


def classify(c, lo, hi) -> str:
    """c=(cx,cy,cz), lo/hi=bbox。Z-up，模型归一到 z∈[0,1.72]。"""
    cx, cy, cz = c
    zx, zy, zz = (hi[i] - lo[i] for i in range(3))
    if cz > 1.48:
        return "HEAD_TOP"          # 头冠 / 发髻 / 头盔顶
    if cz > 1.30:
        return "HEAD"
    # 背后大片垂布：用局部 y 极值 + 纵向跨度判定，泛化不依赖固定朝向
    if zz > 0.55 and (zy > 0.35 or zx > 0.55) and cz < 1.35:
        return "CAPE_OR_PANEL"    # 披风 / 长条布片
    if cz < 0.95 and zz > 0.25 and abs(cx) < 0.40:
        return "SKIRT"            # 长衫下摆 / 腰裙
    if cz < 0.42:
        return "BOOTS"
    return "BODY"


def main() -> int:
    assert BLEND.is_file(), BLEND
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    obj = next(o for o in bpy.context.scene.objects
               if o.type == "MESH"
               and any(m.type == "SURFACE_DEFORM" for m in o.modifiers))
    mesh = obj.data
    nv, npoly = len(mesh.vertices), len(mesh.polygons)
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
        v0 = vs[0]
        for v in vs[1:]:
            union(v0, v)

    verts = defaultdict(list)
    for v in mesh.vertices:
        verts[find(v.index)].append(v.index)

    co = [tuple(v.co) for v in mesh.vertices]
    rows = []
    for root, ids in verts.items():
        xs = [co[i][0] for i in ids]
        ys = [co[i][1] for i in ids]
        zs = [co[i][2] for i in ids]
        lo = [min(xs), min(ys), min(zs)]
        hi = [max(xs), max(ys), max(zs)]
        c = [sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs)]
        rows.append({"root": root, "verts": len(ids),
                     "lo": [round(v, 4) for v in lo],
                     "hi": [round(v, 4) for v in hi],
                     "centroid": [round(v, 4) for v in c],
                     "region": classify(c, lo, hi)})

    by_region = defaultdict(lambda: {"shells": 0, "verts": 0})
    for r in rows:
        b = by_region[r["region"]]
        b["shells"] += 1
        b["verts"] += r["verts"]
    top = sorted(rows, key=lambda r: -r["verts"])[:20]

    # 按区域上色：给每个 polygon 指定 material_index，Workbench MATERIAL 着色。
    palette = {
        "HEAD_TOP": (1.0, 0.15, 0.15, 1.0),
        "HEAD": (1.0, 0.55, 0.10, 1.0),
        "CAPE_OR_PANEL": (0.20, 0.45, 1.0, 1.0),
        "SKIRT": (0.15, 0.95, 0.35, 1.0),
        "BOOTS": (0.85, 0.35, 0.95, 1.0),
        "BODY": (0.75, 0.75, 0.75, 1.0),
    }
    names = list(palette)
    mesh.materials.clear()
    for n in names:
        m = bpy.data.materials.new("J_REGION_" + n)
        m.diffuse_color = palette[n]
        mesh.materials.append(m)
    region_of = {r["root"]: r["region"] for r in rows}
    for p in mesh.polygons:
        p.material_index = names.index(region_of[find(p.vertices[0])])

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "FLAT"
    scene.display.shading.color_type = "MATERIAL"
    scene.render.film_transparent = True
    scene.render.resolution_x = 768
    scene.render.resolution_y = 768
    cam_data = bpy.data.cameras.new("J_CAM")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 2.1
    cam = bpy.data.objects.new("J_CAM", cam_data)
    scene.collection.objects.link(cam)
    cam.location = (0.0, -4.0, 0.95)
    cam.rotation_euler = (1.5707963, 0.0, 0.0)
    scene.camera = cam
    BOARD.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(BOARD)
    bpy.ops.render.render(write_still=True)

    payload = {
        "source_blend": str(BLEND),
        "object": obj.name, "verts": nv, "polygons": npoly,
        "shells": len(rows),
        "by_region": dict(by_region),
        "top20": top,
        "board": str(BOARD),
        "board_bytes": BOARD.stat().st_size if BOARD.is_file() else 0,
        "checks": {
            "opened": nv > 60000,
            "shell_count_matches_2809": len(rows) == 2809,
            "has_head_region": by_region["HEAD_TOP"]["verts"] > 0,
            "has_skirt_region": by_region["SKIRT"]["verts"] > 0,
            "has_cape_region": by_region["CAPE_OR_PANEL"]["verts"] > 0,
            "board_written": BOARD.is_file()
                             and BOARD.stat().st_size > 10000,
        },
    }
    payload["failed"] = [k for k, v in payload["checks"].items() if not v]
    payload["ok"] = not payload["failed"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("SHELLS", len(rows), "VERTS", nv)
    for k, v in by_region.items():
        print("REGION", k, v)
    for k, v in payload["checks"].items():
        print("CHECK", k, v)
    print("SHELLS_J_OK" if payload["ok"] else "SHELLS_J_FAILED")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
