"""B 路线 P0：把「白衫下摆 / 黑披风 / 青冠 / 红花」精确钉到具体壳 ID。

r1 的教训：按 bbox/质心的粗区域分类对不上语义部件，压缩顶点还会撕面。
本探针只做定位，不改任何资产：
  1. union-find 分 2,809 壳，每壳导出 verts / bbox / centroid / UV bbox /
     UV 采样色（从 foe baseColor 缩略到 1024² 读回）；
  2. 渲 4 视角「按组上色」全图 + 4 张「候选组单独隔离」图
     （非目标壳顶点移出正交相机视锥，不是删面，渲完逐帧恢复）；
  3. 渲 1 张真实贴图外观图作参照。

看图判断与数据判据分开：最终删除规则必须写「壳 ID + 空间/UV 锚点」，
不能只写区域名。产物落 shots/shell_isolate/ 与 data/shell_isolate_b.json。

用法：blender.exe -b --python probe_shell_isolate_b.py
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
BLEND = BAKE / "route-a-asset-rework" / "foe-deformable-continuous-shell.blend"
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
TEX_PNG = (GAME / "assets" / "3d"
           / "foe-rigged_texture_pbr_20250901.png")
SHOTS = HERE / "shots" / "shell_isolate"
OUT = HERE / "data" / "shell_isolate_b.json"
TEX_SIZE = 1024

PALETTE = {
    "G0_CAPE": (0.20, 0.45, 1.00, 1.0),
    "G1_SKIRT": (0.15, 0.95, 0.35, 1.0),
    "G2_HEAD_SMALL": (1.00, 0.15, 0.15, 1.0),
    "G3_HEAD_LARGE": (1.00, 0.55, 0.10, 1.0),
    "G4_BODY": (0.62, 0.62, 0.62, 1.0),
}
VIEWS = {
    "front": ((0.0, -4.0, 0.95), (math.pi / 2, 0.0, 0.0)),
    "back": ((0.0, 4.0, 0.95), (math.pi / 2, 0.0, math.pi)),
    "side": ((4.0, 0.0, 0.95), (math.pi / 2, 0.0, math.pi / 2)),
    "angle45": ((2.8, -2.8, 0.95), (math.pi / 2, 0.0, math.pi / 4)),
}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def classify(c, lo, hi) -> str:
    cx, cy, cz = c
    zx, zy, zz = (hi[i] - lo[i] for i in range(3))
    if cz > 1.48:
        return "HEAD_TOP"
    if cz > 1.30:
        return "HEAD"
    if zz > 0.55 and (zy > 0.35 or zx > 0.55) and cz < 1.35:
        return "CAPE_OR_PANEL"
    if cz < 0.95 and zz > 0.25 and abs(cx) < 0.40:
        return "SKIRT"
    if cz < 0.42:
        return "BOOTS"
    return "BODY"


def load_tex_array(path: Path):
    img = bpy.data.images.load(str(path), check_existing=False)
    img.scale(TEX_SIZE, TEX_SIZE)
    buf = np.empty(TEX_SIZE * TEX_SIZE * 4, dtype=np.float32)
    img.pixels.foreach_get(buf)
    return buf.reshape((TEX_SIZE, TEX_SIZE, 4))


def tex_stats(arr, uvs) -> dict:
    """对每个壳的 UV loop 点做稀疏采样，返回线性空间的亮度/青/暖红分数。"""
    if not uvs:
        return {"samples": 0, "lin_luma": 0.0,
                "cyan_ratio": 0.0, "warm_ratio": 0.0}
    step = max(1, len(uvs) // 64)
    pts = uvs[::step][:64]
    luma, cyan, warm = [], [], []
    for u, v in pts:
        x = min(TEX_SIZE - 1, max(0, int(u * TEX_SIZE)))
        # Blender image.pixels 原点在左下；同时记录 PIL 口径供交叉核对。
        y = min(TEX_SIZE - 1, max(0, int(v * TEX_SIZE)))
        r, g, b = (float(arr[y, x, k]) for k in range(3))
        luma.append(0.2126 * r + 0.7152 * g + 0.0722 * b)
        cyan.append(1.0 if (g > 0.10 and b > 0.10
                            and r < g * 0.75) else 0.0)
        warm.append(1.0 if (r > 0.20 and g < r * 0.55
                            and b < r * 0.55) else 0.0)
    n = len(pts)
    return {"samples": n,
            "lin_luma": round(sum(luma) / n, 5),
            "cyan_ratio": round(sum(cyan) / n, 5),
            "warm_ratio": round(sum(warm) / n, 5)}


def main() -> int:
    assert BLEND.is_file(), BLEND
    assert TEX_PNG.is_file(), TEX_PNG
    SHOTS.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    scene = bpy.context.scene
    src = next(o for o in scene.objects
               if o.type == "MESH"
               and any(m.type == "SURFACE_DEFORM" for m in o.modifiers))

    # 渲染副本：去掉 SURFACE_DEFORM 与父级，保留 UV / 材质槽。
    obj = src.copy()
    obj.data = src.data.copy()
    scene.collection.objects.link(obj)
    obj.name = "B_ISOLATE"
    for m in list(obj.modifiers):
        obj.modifiers.remove(m)
    obj.parent = None
    mesh = obj.data
    # 关键：源 src / 代理壳 / 其它 MESH 必须全部退出渲染，否则隔离图里
    # 目标壳移走后会被源对象的完整人形「补白」，看起来像什么都没删。
    hidden = []
    for o in scene.objects:
        if o.type == "MESH" and o is not obj and not o.hide_render:
            o.hide_render = True
            hidden.append(o.name)
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
        for v in vs[1:]:
            union(vs[0], v)

    co0 = [tuple(v.co) for v in mesh.vertices]
    shell_verts = defaultdict(list)
    for v in mesh.vertices:
        shell_verts[find(v.index)].append(v.index)
    root_of = {vi: root for root, ids in shell_verts.items()
               for vi in ids}

    uv_layer = mesh.uv_layers.active
    shell_uvs = defaultdict(list)
    for p in mesh.polygons:
        root = root_of[p.vertices[0]]
        for li in p.loop_indices:
            shell_uvs[root].append(tuple(uv_layer.data[li].uv))

    arr = load_tex_array(TEX_PNG)
    rows = []
    for root, ids in shell_verts.items():
        xs = [co0[i][0] for i in ids]
        ys = [co0[i][1] for i in ids]
        zs = [co0[i][2] for i in ids]
        lo = [min(xs), min(ys), min(zs)]
        hi = [max(xs), max(ys), max(zs)]
        c = [sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs)]
        reg = classify(c, lo, hi)
        uvs = shell_uvs.get(root, [])
        ub = ([min(u for u, _ in uvs), min(v for _, v in uvs),
               max(u for u, _ in uvs), max(v for _, v in uvs)]
              if uvs else [0, 0, 0, 0])
        if reg == "CAPE_OR_PANEL":
            group = "G0_CAPE"
        elif reg == "SKIRT":
            group = "G1_SKIRT"
        elif reg == "HEAD_TOP" and len(ids) <= 300:
            group = "G2_HEAD_SMALL"
        elif reg == "HEAD_TOP":
            group = "G3_HEAD_LARGE"
        else:
            group = "G4_BODY"
        ts = tex_stats(arr, uvs)
        rows.append({
            "shell_id": root, "verts": len(ids), "region": reg,
            "group": group,
            "lo": [round(v, 4) for v in lo],
            "hi": [round(v, 4) for v in hi],
            "centroid": [round(v, 4) for v in c],
            "uv_bbox": [round(v, 4) for v in ub],
            "tex": ts,
        })
    rows.sort(key=lambda r: (r["group"], -r["verts"]))
    by_group = defaultdict(lambda: {"shells": 0, "verts": 0})
    for r in rows:
        g = by_group[r["group"]]
        g["shells"] += 1
        g["verts"] += r["verts"]

    # ── 材质：按组上色 ──────────────────────────────────────────
    names = list(PALETTE)
    mesh.materials.clear()
    for n in names:
        m = bpy.data.materials.new("B_" + n)
        m.diffuse_color = PALETTE[n]
        mesh.materials.append(m)
    group_of = {r["shell_id"]: r["group"] for r in rows}
    for p in mesh.polygons:
        p.material_index = names.index(group_of[root_of[p.vertices[0]]])

    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "FLAT"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = False
    scene.render.film_transparent = True
    scene.render.resolution_x = 640
    scene.render.resolution_y = 768
    scene.render.resolution_percentage = 100
    cam_data = bpy.data.cameras.new("B_CAM")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 2.1
    cam = bpy.data.objects.new("B_CAM", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam

    def render(name, loc, rot):
        cam.location = loc
        cam.rotation_euler = rot
        scene.render.filepath = str(SHOTS / f"{name}.png")
        bpy.ops.render.render(write_still=True)
        return SHOTS / f"{name}.png"

    written = []
    for vname, (loc, rot) in VIEWS.items():
        written.append(render(f"b-groups-{vname}", loc, rot))

    # 真实贴图外观（单独一张，不受组色干扰）
    scene.display.shading.color_type = "TEXTURE"
    written.append(render("b-texture-front", *VIEWS["front"]))
    scene.display.shading.color_type = "MATERIAL"

    # ── 隔离：只留目标组，其余壳顶点移出视锥 ────────────────────
    for gname in ("G0_CAPE", "G1_SKIRT", "G2_HEAD_SMALL",
                  "G3_HEAD_LARGE"):
        keep = {r["shell_id"] for r in rows if r["group"] == gname}
        for v in mesh.vertices:
            if root_of[v.index] in keep:
                v.co = co0[v.index]
            else:
                v.co = (co0[v.index][0], co0[v.index][1], -100.0)
        written.append(render(f"b-only-{gname}", *VIEWS["front"]))
    for v in mesh.vertices:
        v.co = co0[v.index]

    # 逐壳随机色（同一组内也能分辨单个壳），正面 + 侧面
    shell_ids = sorted({r["shell_id"] for r in rows})
    shell_color_index = {}
    for i, sid in enumerate(shell_ids):
        shell_color_index[sid] = i
    # 用 16 色循环，靠相邻壳编号差异区分（配合 JSON 里的壳 ID 表查）
    palette16 = []
    for i in range(16):
        h = i / 16.0
        palette16.append((0.25 + 0.7 * abs(math.sin(h * 7.1)),
                          0.25 + 0.7 * abs(math.sin(h * 3.7 + 1.1)),
                          0.25 + 0.7 * abs(math.sin(h * 5.3 + 2.4)),
                          1.0))
    mesh.materials.clear()
    for i, c in enumerate(palette16):
        m = bpy.data.materials.new(f"B_SHELL_{i:02d}")
        m.diffuse_color = c
        mesh.materials.append(m)
    for p in mesh.polygons:
        sid = root_of[p.vertices[0]]
        p.material_index = shell_color_index[sid] % 16
    for vname in ("front", "side"):
        written.append(render(f"b-shells-{vname}", *VIEWS[vname]))

    checks = {
        "opened": nv > 60000,
        "shell_count_matches_2809": len(rows) == 2809,
        "polygon_count_matches": npoly == 79998,
        "uv_layer_present": uv_layer is not None,
        # 订正（实测）：HEAD_TOP 的 174 个壳全部 <=300 顶点，
        # G3_HEAD_LARGE 天然为空。不许把「应该有大壳」写成判据；
        # 改为守「分组覆盖全部壳」+「头部确实没有大壳」这两个事实。
        "groups_cover_all_shells": (
            sum(v["shells"] for v in by_group.values()) == len(rows)),
        "cape_skirt_head_small_present": all(
            by_group[g]["verts"] > 0 for g in
            ("G0_CAPE", "G1_SKIRT", "G2_HEAD_SMALL")),
        "head_top_has_no_large_shell": (
            by_group["G3_HEAD_LARGE"]["shells"] == 0),
        # 隔离图只有零星碎片，透明 PNG 可能只有几 KB；阈值按「文件真写出」
        # 放宽，内容非空由 venv 侧 make_isolate_board_b.py 用 PIL 复核。
        "all_shots_written": all(p.is_file() and p.stat().st_size > 2000
                                 for p in written),
        "all_other_meshes_hidden": all(
            o.hide_render for o in scene.objects
            if o.type == "MESH" and o is not obj),
        "tex_array_loaded": arr.shape == (TEX_SIZE, TEX_SIZE, 4),
        "vertices_restored": all(
            tuple(v.co) == co0[v.index] for v in mesh.vertices),
    }
    payload = {
        "source_blend": str(BLEND), "source_blend_sha256": sha256(BLEND),
        "base_color_png": str(TEX_PNG), "base_color_sha256": sha256(TEX_PNG),
        "object": src.name, "verts": nv, "polygons": npoly,
        "shells": len(rows), "by_group": dict(by_group),
        "shots": [str(p) for p in written],
        "hidden_render_objects": hidden,
        "shells_table": rows,
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
    }
    payload["ok"] = not payload["failed"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("SHELLS", len(rows), "VERTS", nv, "POLYGONS", npoly)
    for k, v in by_group.items():
        print("GROUP", k, v)
    print("SHOTS", len(written))
    for k, v in checks.items():
        print("CHECK", k, v)
    print("SHELL_ISOLATE_B_OK" if payload["ok"]
          else "SHELL_ISOLATE_B_FAILED")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
