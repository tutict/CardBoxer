"""J 路线 P0：先查清「两人看起来同源」到底同源在哪，不先动任何资产。

三件事：
  1. 把 I 路线同进程 A/B 的左右角色 ROI 裁出来放大，肉眼看清敌我造型。
  2. 纯 Python 解析三份 GLB 的 JSON chunk：顶点数 / POSITION bbox /
     skin / node 名 / 贴图引用，确认游戏里 foe 用的是哪份几何。
  3. 对照 11-08 图生 3D 原始产物与 A/H 路线导出记录，判定
     「造型雷同」是几何同源、贴图同源，还是渲染把细节吃掉了。

只读，不写游戏工程、不改任何归档。用法：python diag_shape_root.py
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
I = BAKE / "I路线-视觉区分度"
H = BAKE / "H路线-双方3D侧面战斗"
FOE_V1 = BAKE / "对手怪Blender建模V1"
SHOTS = I / "shots" / "visual_ab"
BOARD = HERE / "boards" / "J-现状左右特写.png"
OUT = HERE / "data" / "shape_root_j.json"
FONT = Path(r"C:\Windows\Fonts\msyh.ttc")


def glb_json(path: Path) -> dict:
    raw = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", raw, 0)
    assert magic == b"glTF" and version == 2 and length == len(raw)
    off = 12
    while off < len(raw):
        clen, ctype = struct.unpack_from("<I4s", raw, off)
        off += 8
        if ctype == b"JSON":
            return json.loads(raw[off:off + clen].decode("utf-8"))
        off += clen
    raise ValueError(f"no JSON chunk in {path}")


def shape(path: Path) -> dict:
    g = glb_json(path)
    prim = g["meshes"][0]["primitives"][0]
    pos = g["accessors"][prim["attributes"]["POSITION"]]
    return {
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "verts": pos["count"],
        "pos_min": pos.get("min"),
        "pos_max": pos.get("max"),
        "bbox_xyz": [round(pos["max"][i] - pos["min"][i], 6)
                     for i in range(3)],
        "attributes": sorted(prim["attributes"].keys()),
        "skins": len(g.get("skins", [])),
        "animations": len(g.get("animations", [])),
        "nodes": len(g.get("nodes", [])),
        "node_names": [n.get("name", "") for n in g.get("nodes", [])][:20],
        "images": [im.get("name", "") for im in g.get("images", [])],
        "materials": len(g.get("materials", [])),
    }


def main() -> int:
    roi = json.loads((H / "data" / "roi_h.json").read_text(
        encoding="utf-8"))["boxes"]
    plain = Image.open(SHOTS / "vis-plain.png").convert("RGB")
    on = Image.open(SHOTS / "vis-on.png").convert("RGB")
    z, pad, label = 3, 20, 36
    w, h = (roi[0][2] - roi[0][0]) * z, (roi[0][3] - roi[0][1]) * z
    cw, ch = 2 * w + 3 * pad, 2 * (h + label) + 3 * pad
    canvas = Image.new("RGB", (cw, ch), (24, 28, 38))
    d = ImageDraw.Draw(canvas)
    f = ImageFont.truetype(str(FONT), 20) if FONT.is_file() \
        else ImageFont.load_default()
    cells = [
        (plain, roi[0], "玩家 · plain（未调色）", pad, pad),
        (plain, roi[1], "对手 · plain（未调色 / H 原样）", 2 * pad + w, pad),
        (on, roi[0], "玩家 · on", pad, 2 * pad + h + label),
        (on, roi[1], "对手 · on（I 调色后）", 2 * pad + w,
         2 * pad + h + label),
    ]
    for im, box, text, x, y in cells:
        crop = im.crop(box).resize((w, h), Image.LANCZOS)
        canvas.paste(crop, (x, y))
        d.text((x + 4, y + h + 4), text, font=f, fill=(190, 200, 220))
    BOARD.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(BOARD)

    glbs = {
        "game_player": GAME / "assets/3d/player-rigged.glb",
        "game_foe": GAME / "assets/3d/foe-rigged.glb",
        "foe_v1_source": FOE_V1 / "artifact_03.glb",
    }
    shapes = {k: shape(p) for k, p in glbs.items()}
    h_inspect = json.loads((H / "data" / "foe_gltf_inspection.json").read_text(
        encoding="utf-8"))
    v1_inspect = json.loads((FOE_V1 / "model_inspection.json").read_text(
        encoding="utf-8"))
    base_png = GAME / "assets/3d/foe-rigged_texture_pbr_20250901.png"

    checks = {
        "three_glbs_parsed": len(shapes) == 3,
        "game_foe_has_skin": shapes["game_foe"]["skins"] == 1,
        "game_foe_verts_match_v1_source": (
            shapes["game_foe"]["verts"]
            == v1_inspect["vertices_total"] + 35),
        "source_model_is_unskinned": (
            shapes["foe_v1_source"]["skins"] == 0
            and v1_inspect["has_skin"] is False),
        "foe_and_player_geometry_differ": (
            shapes["game_foe"]["verts"] != shapes["game_player"]["verts"]),
        "foe_basecolor_size_matches_v1_zip": (
            base_png.stat().st_size
            == next(e["size"] for e in v1_inspect["zip_entries"]
                    if e["name"] == "texture_pbr_20250901.png")),
        "h_export_verts_match_game_glb": (
            h_inspect["foe"]["primitives"][0]["verts"]
            == shapes["game_foe"]["verts"]),
        "board_written": BOARD.is_file() and BOARD.stat().st_size > 100000,
    }
    payload = {
        "roi": roi, "board": str(BOARD),
        "board_bytes": BOARD.stat().st_size,
        "shapes": shapes,
        "h_inspect_foe": h_inspect["foe"],
        "v1_source_inspect": {
            "vertices_total": v1_inspect["vertices_total"],
            "connected_shells_unionfind":
                v1_inspect["connected_shells_unionfind"],
            "has_skin": v1_inspect["has_skin"],
        },
        "foe_basecolor_png_bytes": base_png.stat().st_size,
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k, v in shapes.items():
        print("GLB", k, "verts", v["verts"], "bbox", v["bbox_xyz"],
              "skins", v["skins"], "images", v["images"])
    for k, v in checks.items():
        print("CHECK", k, v)
    print("SHAPE_ROOT_J_OK" if payload["ok"] else "SHAPE_ROOT_J_FAILED")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
