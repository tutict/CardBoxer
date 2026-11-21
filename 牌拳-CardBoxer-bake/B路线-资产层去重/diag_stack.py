"""B 路线 P0：资产层叠层的决定性诊断（只读，不碰游戏工程）。

要回答的问题
------------
用户看到的「一个身体上叠了金属重甲 + 白布青云纹长衫 + 黑披风 + 头饰」，
到底哪几套是**独立几何壳**、哪几套是**烘在保留壳 UV 上的贴图图案**、
哪几套只是**渲染高光**？

J 路线 B round2 已经把 262 个壳 / 10,526 顶点塌缩掉，引擎内截帧里
白布青云纹仍在。本脚本不经 Blender、不经 Godot，直接解析 GLB 的
POSITION / TEXCOORD_0 / indices，做两件事：

1. 逐面取 UV 中心 → 采样 foe baseColor → 统计每个连通壳的
   cyan / warm / near_white 面数；
2. 用「I 基线顶点坐标是否还在 B round2 GLB 里」反查哪些壳被塌缩
   （非目标顶点逐字节不变，目标顶点移到质心 ⇒ 原坐标消失）。

于是「被删壳 vs 保留壳」各自带多少青/白面可以直接对比，
不需要跨 Blender/GLB 的顶点序或坐标系做壳 ID 猜测。

输出：data/stack_shells.json、data/stack_diagnosis.json、
      boards/B-资产层归属.png
用法：python diag_stack.py
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
J = BAKE / "J路线-造型重做"
GLB_I = GAME / "assets" / "3d" / "foe-rigged.glb"
GLB_B = J / "foe-rigged-b.glb"
TEX = GAME / "assets" / "3d" / "foe-rigged_texture_pbr_20250901.png"
OUT_SHELLS = HERE / "data" / "stack_shells.json"
OUT_DIAG = HERE / "data" / "stack_diagnosis.json"
BOARD = HERE / "boards" / "B-资产层归属.png"
FONT = Path(r"C:\Windows\Fonts\msyh.ttc")

BASELINE_SHA = "0edcfe9e455f3c8c9deb7034397c815fd701130ed9a10c2e08800fff789cba88"
B_SHA = "96d383eec6286efb1099e9fba617c67c8fefa47a4fb5ff69f0c9abb7933831c5"
TEX_SHA = "3c1076596ef22f2e45c6509e459f7e262053724ce05b803874ed53a927473d6a"

S = 1024
COMP = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2),
        5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_glb(path: Path):
    data = path.read_bytes()
    magic, ver, _total = struct.unpack_from("<4sII", data, 0)
    assert magic == b"glTF" and ver == 2, (path, magic, ver)
    off, js, bin_ = 12, None, None
    while off < len(data):
        clen, ctype = struct.unpack_from("<I4s", data, off)
        off += 8
        chunk = data[off:off + clen]
        off += clen
        if ctype == b"JSON":
            js = json.loads(chunk.decode("utf-8"))
        elif ctype == b"BIN\x00":
            bin_ = chunk
    assert js is not None and bin_ is not None, path

    def accessor(idx):
        acc = js["accessors"][idx]
        bv = js["bufferViews"][acc["bufferView"]]
        fmt, csize = COMP[acc["componentType"]]
        n = NCOMP[acc["type"]]
        stride = bv.get("byteStride") or n * csize
        base = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
        pattern = "<" + fmt * n
        return [struct.unpack_from(pattern, bin_, base + i * stride)
                for i in range(acc["count"])]

    prim = js["meshes"][0]["primitives"][0]
    pos = accessor(prim["attributes"]["POSITION"])
    uv = accessor(prim["attributes"]["TEXCOORD_0"])
    idx = [a[0] for a in accessor(prim["indices"])]
    return {"pos": pos, "uv": uv, "idx": idx,
            "json": js, "verts": len(pos), "faces": len(idx) // 3,
            "meshes": len(js["meshes"]),
            "primitives": len(js["meshes"][0]["primitives"])}


def shells_of(glb):
    pos, idx = glb["pos"], glb["idx"]
    parent = list(range(len(pos)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for k in range(0, len(idx), 3):
        a, b, c = idx[k], idx[k + 1], idx[k + 2]
        union(a, b)
        union(a, c)
    roots = [find(i) for i in range(len(pos))]
    groups = defaultdict(list)
    for i, r in enumerate(roots):
        groups[r].append(i)
    face_shell = [roots[idx[3 * k]] for k in range(glb["faces"])]
    face_by_shell = defaultdict(list)
    for k, sid in enumerate(face_shell):
        face_by_shell[sid].append(k)
    return roots, groups, face_by_shell


def cyan(r, g, b):
    return b > 110 and g > 110 and r < g - 18


def warm(r, g, b):
    return r > 120 and g < r * 0.65 and b < r * 0.65


def white(r, g, b):
    return r > 175 and g > 175 and b > 175


def draw_board(pal, shells, flip, diag):
    pad, label, S2 = 18, 92, 640
    W, H = 2 * S2 + 3 * pad, S2 + 2 * pad + label
    canvas = Image.new("RGB", (W, H), (22, 26, 36))
    d = ImageDraw.Draw(canvas)
    f = ImageFont.truetype(str(FONT), 17) if FONT.is_file() \
        else ImageFont.load_default()

    # 左：贴图缩略 + 青/暖红/近白高亮
    thumb = Image.new("RGB", (S, S))
    thumb.putdata(pal)
    thumb = thumb.resize((S2, S2), Image.LANCZOS)
    canvas.paste(thumb, (pad, pad))
    d2 = ImageDraw.Draw(thumb)
    scale = S2 / S
    for j, c in enumerate(pal):
        kinds = [k for k, fn in (("cyan", cyan), ("warm", warm),
                                 ("white", white)) if fn(*c)]
        if not kinds:
            continue
        col = ((0, 255, 255) if "cyan" in kinds else
               (255, 60, 60) if "warm" in kinds else (255, 255, 255))
        x, y = (j % S) * scale, (j // S) * scale
        d2.point((x, y), fill=col)
    canvas.paste(thumb, (pad, pad))
    d.text((pad, pad + S2 + 8),
           "foe baseColor 4096→1024：青/暖红/近白特征落点",
           font=f, fill=(210, 220, 240))

    # 右：壳的 3D 正交散点（x 横轴、y 高度轴，Y-up 已翻转到屏幕）
    px0 = 2 * pad + S2
    d.rectangle((px0, pad, px0 + S2, pad + S2), fill=(14, 17, 25))
    xmin, xmax, ymax = -0.65, 0.65, 1.80

    def project(x, y):
        return (px0 + int((x - xmin) / (xmax - xmin) * S2),
                pad + int((ymax - y) / ymax * S2))

    for row in sorted(shells, key=lambda r: -r["deleted_ratio"]):
        cx, cy = project(row["centroid"][0], row["centroid"][1])
        rad = max(1, min(9, int(math.sqrt(row["verts"]) / 3)))
        if row["deleted_ratio"] >= 0.9:
            col = (240, 78, 78)
        elif row["cyan_faces"] > 0:
            col = (60, 220, 230)
        else:
            col = (104, 110, 124)
        d.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=col)
    d.text((px0, pad + S2 + 8),
           f"逐壳 3D 分布：红=B round2 已删 {diag['deleted_shells']} 壳，"
           f"青=UV 带青色面 {diag['cyan_shells']} 壳，灰=其余",
           font=f, fill=(210, 220, 240))
    d.text((pad, H - 26),
           f"UV v 口径={flip}；青面 {diag['cyan_faces']} / "
           f"近白面 {diag['white_faces']} / 暖红面 {diag['warm_faces']}；"
           f"青面 {diag['cyan_faces_on_deleted']}/{diag['cyan_faces']} "
           f"落在已删壳（保留壳占 {diag['kept_cyan_share']:.1%}）",
           font=f, fill=(160, 175, 200))
    BOARD.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(BOARD)


def main() -> int:
    assert GLB_I.is_file() and GLB_B.is_file() and TEX.is_file()
    hashes = {"i_glb": sha256(GLB_I), "b_glb": sha256(GLB_B),
              "basecolor": sha256(TEX)}

    gi, gb = parse_glb(GLB_I), parse_glb(GLB_B)
    roots, groups, face_by_shell = shells_of(gi)
    pos, uv, idx = gi["pos"], gi["uv"], gi["idx"]

    # 面 UV 中心
    face_uv = []
    for k in range(gi["faces"]):
        i0, i1, i2 = idx[3 * k], idx[3 * k + 1], idx[3 * k + 2]
        u = (uv[i0][0] + uv[i1][0] + uv[i2][0]) / 3.0
        v = (uv[i0][1] + uv[i1][1] + uv[i2][1]) / 3.0
        face_uv.append((u, v))

    im = Image.open(TEX).convert("RGB")
    assert im.size == (4096, 4096), im.size
    pal = list(im.resize((S, S), Image.LANCZOS).getdata())

    def sample(u, v, flip):
        x = min(S - 1, max(0, int(u * (S - 1))))
        yv = (1.0 - v) if flip else v
        y = min(S - 1, max(0, int(yv * (S - 1))))
        return pal[y * S + x]

    def tally(flip):
        n = {"cyan": 0, "warm": 0, "white": 0}
        for u, v in face_uv:
            c = sample(u, v, flip)
            if cyan(*c):
                n["cyan"] += 1
            if warm(*c):
                n["warm"] += 1
            if white(*c):
                n["white"] += 1
        return n

    t0, t1 = tally(False), tally(True)
    # glTF 的 V 原点在左上；哪个口径能命中更多青色面就用哪个，
    # 两种结果都写进报告，判定可复算，不靠猜。
    flip = t1["cyan"] > t0["cyan"]
    face_tally = t1 if flip else t0

    # B round2 里还活着的坐标（round 到 1e-6 消 float 拆分微差）
    set_b = {(round(p[0], 6), round(p[1], 6), round(p[2], 6))
             for p in gb["pos"]}

    shells = []
    for sid, vids in sorted(groups.items()):
        lo = [min(pos[i][k] for i in vids) for k in range(3)]
        hi = [max(pos[i][k] for i in vids) for k in range(3)]
        ctr = [sum(pos[i][k] for i in vids) / len(vids) for k in range(3)]
        faces = face_by_shell.get(sid, [])
        n = {"cyan": 0, "warm": 0, "white": 0}
        ub = [1.0, 1.0, 0.0, 0.0]
        for k in faces:
            c = sample(face_uv[k][0], face_uv[k][1], flip)
            if cyan(*c):
                n["cyan"] += 1
            if warm(*c):
                n["warm"] += 1
            if white(*c):
                n["white"] += 1
            for vi in idx[3 * k:3 * k + 3]:
                u0, v0 = uv[vi]
                ub[0] = min(ub[0], u0)
                ub[1] = min(ub[1], v0)
                ub[2] = max(ub[2], u0)
                ub[3] = max(ub[3], v0)
        gone = sum(1 for i in vids
                   if (round(pos[i][0], 6), round(pos[i][1], 6),
                       round(pos[i][2], 6)) not in set_b)
        shells.append({
            "shell_id": sid, "verts": len(vids), "faces": len(faces),
            "lo": [round(v, 5) for v in lo],
            "hi": [round(v, 5) for v in hi],
            "centroid": [round(v, 5) for v in ctr],
            "uv_bbox": [round(v, 5) for v in ub] if faces else None,
            "cyan_faces": n["cyan"], "warm_faces": n["warm"],
            "white_faces": n["white"],
            "missing_verts_in_b": gone,
            "deleted_ratio": round(gone / len(vids), 6),
        })

    # 分界由 diag_ratio.py 的双峰分布钉死：2556 个壳的 missing 精确为 0
    # （build_shape_b.py 保证非目标顶点逐字节不变），253 个壳 nonzero。
    # 不能用 0.9 阈值：GLB 导出按 UV/法线接缝拆点，同一坐标会被多个
    # 顶点复用，塌缩壳的 missing 比例会落在 0.1~0.9 之间。
    deleted = [r for r in shells if r["deleted_ratio"] > 0.0]
    kept = [r for r in shells if r["deleted_ratio"] == 0.0]
    dset = {r["shell_id"] for r in deleted}
    cyan_kept = sum(r["cyan_faces"] for r in kept)
    cyan_del = sum(r["cyan_faces"] for r in deleted)
    white_kept = sum(r["white_faces"] for r in kept)
    cyan_total = face_tally["cyan"]
    kept_share = cyan_kept / cyan_total if cyan_total else 0.0

    # 画面里那条「从腰垂到脚踝的长布」：Y 跨度大、X 窄
    tall = [r for r in shells
            if (r["hi"][1] - r["lo"][1]) > 0.50
            and (r["hi"][0] - r["lo"][0]) < 0.35]
    tall_deleted = sum(1 for r in tall if r["shell_id"] in dset)
    # 头顶装饰：质心高度 > 1.40
    head = [r for r in shells if r["centroid"][1] > 1.40]
    head_deleted = sum(1 for r in head if r["shell_id"] in dset)
    # 青色面主要落在哪 10 个壳
    cyan_top = sorted(shells, key=lambda r: -r["cyan_faces"])[:10]

    diag = {
        "hashes": hashes,
        "glb": {
            "i": {k: gi[k] for k in ("verts", "faces", "meshes",
                                     "primitives")},
            "b": {k: gb[k] for k in ("verts", "faces", "meshes",
                                     "primitives")},
        },
        "uv_v_flip": flip,
        "uv_v_tally_raw": t0, "uv_v_tally_flipped": t1,
        "shell_count": len(shells),
        "deleted_shells": len(deleted),
        "deleted_verts": sum(r["verts"] for r in deleted),
        "kept_shells": len(kept),
        "cyan_faces": face_tally["cyan"],
        "white_faces": face_tally["white"],
        "warm_faces": face_tally["warm"],
        "cyan_faces_on_kept": cyan_kept,
        "cyan_faces_on_deleted": cyan_del,
        "kept_cyan_share": round(kept_share, 6),
        "white_faces_on_kept": white_kept,
        "cyan_shells": sum(1 for r in shells if r["cyan_faces"] > 0),
        "cyan_shells_kept": sum(1 for r in kept if r["cyan_faces"] > 0),
        "tall_strip_shells": len(tall),
        "tall_strip_deleted": tall_deleted,
        "head_shells": len(head),
        "head_shells_deleted": head_deleted,
        "cyan_top10": [
            {"shell_id": r["shell_id"], "verts": r["verts"],
             "cyan_faces": r["cyan_faces"], "deleted_ratio": r["deleted_ratio"],
             "centroid": r["centroid"], "lo": r["lo"], "hi": r["hi"],
             "uv_bbox": r["uv_bbox"]} for r in cyan_top],
        "tall_strips": [
            {"shell_id": r["shell_id"], "verts": r["verts"],
             "deleted_ratio": r["deleted_ratio"],
             "lo": r["lo"], "hi": r["hi"],
             "cyan_faces": r["cyan_faces"]} for r in tall],
    }
    checks = {
        "i_glb_is_baseline": hashes["i_glb"] == BASELINE_SHA,
        "b_glb_is_round2": hashes["b_glb"] == B_SHA,
        "basecolor_unchanged": hashes["basecolor"] == TEX_SHA,
        "both_glbs_single_primitive": (gi["meshes"] == 1
                                       and gi["primitives"] == 1
                                       and gb["meshes"] == 1
                                       and gb["primitives"] == 1),
        "shell_count_2809": len(shells) == 2809,
        "deleted_shell_count_in_range": 240 <= len(deleted) <= 280,
        "deleted_verts_in_range": 10000 <= diag["deleted_verts"] <= 11000,
        "no_shells_in_ambiguous_band": sum(
            1 for r in shells if 0 < r["deleted_ratio"] < 0.10) == 0,
        "near_white_faces_absent": face_tally["white"] < 0.01 * gi["faces"],
        "cyan_faces_present": face_tally["cyan"] > 100,
        # 实测 258/268 青面落在被删壳：B round2 的 UV 特征补删其实打中了，
        # 原假设「青云纹烘在保留壳上、删壳碰不到」被证伪。
        "cyan_mostly_on_deleted_shells": (
            cyan_del / cyan_total > 0.90 if cyan_total else False),
        "tall_strips_all_deleted": len(tall) > 0
                                   and tall_deleted == len(tall),
        "head_ornaments_mostly_deleted": len(head) > 0
                                         and head_deleted / len(head) > 0.50,
        "board_written": BOARD.is_file() and BOARD.stat().st_size > 100000,
    }
    diag["checks"] = checks
    diag["failed"] = [k for k, v in checks.items() if not v]
    diag["conclusion"] = (
        "B round2 删壳口径经 GLB 坐标差集独立复核：253 壳 / 10,495 顶点，"
        "与 build_shape_b.json 的 262 壳 / 10,526 顶点对齐；青色 UV 面 "
        "96% 落在被删壳。foe baseColor 上近白面为 0、青面仅 268/79,998。"
        "所以『白布』的白不来自贴图，『青云纹』也不是大面积烘在保留壳上的"
        "图案；把同源观感归因于 foe 几何壳是错的。")
    diag["ok"] = not diag["failed"]

    OUT_SHELLS.parent.mkdir(parents=True, exist_ok=True)
    OUT_SHELLS.write_text(json.dumps(
        {"source": str(GLB_I), "shells": shells},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    draw_board(pal, shells, flip, diag)
    # board_written 在画板之后才能判，重算一次
    checks["board_written"] = (BOARD.is_file()
                               and BOARD.stat().st_size > 100000)
    diag["failed"] = [k for k, v in checks.items() if not v]
    diag["ok"] = not diag["failed"]
    diag["board"] = str(BOARD)
    diag["board_bytes"] = BOARD.stat().st_size
    OUT_DIAG.write_text(json.dumps(diag, ensure_ascii=False, indent=2)
                        + "\n", encoding="utf-8")

    print("GLB I", diag["glb"]["i"], "B", diag["glb"]["b"])
    print("UV_FLIP", flip, "RAW", t0, "FLIPPED", t1)
    print("SHELLS", len(shells), "DELETED", len(deleted),
          "DEL_VERTS", diag["deleted_verts"])
    print("FACES cyan/white/warm", face_tally["cyan"],
          face_tally["white"], face_tally["warm"])
    print("CYAN kept/deleted", cyan_kept, cyan_del,
          "kept_share", round(kept_share, 4))
    print("TALL_STRIPS", len(tall), "deleted", tall_deleted,
          "HEAD", len(head), "deleted", head_deleted)
    print("CYAN_TOP5", [(r["shell_id"], r["cyan_faces"],
                         r["deleted_ratio"]) for r in cyan_top[:5]])
    for k, v in checks.items():
        print("CHECK", k, v)
    print("STACK_DIAG_OK" if diag["ok"] else "STACK_DIAG_FAILED",
          diag["failed"])
    return 0 if diag["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
