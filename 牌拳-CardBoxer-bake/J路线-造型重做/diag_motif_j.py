"""J 路线 r2：定位「同源观感」在贴图还是在几何，并量化 J-01~J-04 基线。

背景（r1 负结果后必须重新问的问题）：
  * r1 用壳级顶点压缩做「去同源」手术，把黑披风撕成尖刺碎片，
    白衫下摆 / 青云纹 / 青结晶头冠 / 红花一个都没消掉。已回滚。
  * diag_texture_pair_j.py 已经预警过：foe baseColor 整体是暗灰重装，
    512 缩略近白占比 0.0%，player 才是大面积白衫青云纹。
    若渲染里 foe 侧仍有纯白长条 + 亮青云纹，则同源不是「造型整体同源」。

本脚本只读，回答三件事：
  A. 4096² 贴图上，近白 / 青 / 高饱和暖红特征像素有多少、聚在哪几个 UV 区。
  B. v1 引擎内 SubViewport 角色掩膜里，这些特征占多少（J-02/J-03 基线）。
  C. 两侧正视剪影 IoU 与肩宽/身高比（J-01 基线），确定剪影本来是否已可分。

输出：data/motif_baseline_j.json、boards/J-同源元素定位.png。
用法：python diag_motif_j.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
V1 = HERE / "shots" / "asset_v1"
BOARD = HERE / "boards" / "J-同源元素定位.png"
OUT = HERE / "data" / "motif_baseline_j.json"
FONT = Path(r"C:\Windows\Fonts\msyh.ttc")

TEX = {
    "player": "player-rigged_texture_pbr_20250901.png",
    "foe": "foe-rigged_texture_pbr_20250901.png",
}
SV = {"player": "j-sv-player.png", "foe": "j-sv-foe.png"}
GRID = 4
TILE = 1024


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_near_white(r, g, b):
    return r > 200 and g > 200 and b > 200


def is_cyan(r, g, b):
    return b > 120 and g > 120 and r < g - 20


def is_hot_red(r, g, b):
    return r > 140 and g < r * 0.62 and b < r * 0.62


def texture_features(path: Path) -> dict:
    im = Image.open(path).convert("RGB")
    small = im.resize((TILE, TILE), Image.LANCZOS)
    px = list(small.getdata())
    n = len(px)
    counts = {"near_white": 0, "cyan": 0, "hot_red": 0}
    grid = [[0] * GRID for _ in range(GRID)]
    cell_px = TILE // GRID
    for i, (r, g, b) in enumerate(px):
        hit = (is_near_white(r, g, b) or is_cyan(r, g, b)
               or is_hot_red(r, g, b))
        if is_near_white(r, g, b):
            counts["near_white"] += 1
        if is_cyan(r, g, b):
            counts["cyan"] += 1
        if is_hot_red(r, g, b):
            counts["hot_red"] += 1
        if hit:
            grid[(i // TILE) // cell_px][(i % TILE) // cell_px] += 1
    return {
        "file": path.name, "orig_size": list(im.size),
        "sha256": sha256(path), "analyzed_size": [TILE, TILE],
        "counts": counts,
        "ratios": {k: round(v / n, 6) for k, v in counts.items()},
        "motif_grid": grid,
        "grid_max": max(max(row) for row in grid),
    }


def character_mask(im: Image.Image) -> list[bool]:
    """从 SubViewport PNG 提取角色掩膜：优先 alpha，否则按非近白背景。"""
    w, h = im.size
    if im.mode == "RGBA":
        a = list(im.getchannel("A").getdata())
        alpha_min, alpha_max = min(a), max(a)
        if alpha_max - alpha_min > 32:
            return [v > 127 for v in a], "alpha>127", [alpha_min, alpha_max]
    rgb = list(im.convert("RGB").getdata())
    # 背景是纯白（或近白）；角色像素取「明显偏离白」的。
    out = [not (r > 246 and g > 246 and b > 246) for r, g, b in rgb]
    return out, "not_near_white_bg", None


def silhouette_stats(im: Image.Image) -> dict:
    w, h = im.size
    mask, mask_kind, alpha_range = character_mask(im)
    rows = [mask[y * w:(y + 1) * w] for y in range(h)]
    ys = [y for y, row in enumerate(rows) if any(row)]
    xs = [x for row in rows for x, v in enumerate(row) if v]
    if not ys or not xs:
        return {"mask_kind": mask_kind, "error": "empty mask"}
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    height = y1 - y0 + 1
    # 肩宽：顶部 15%~32% 区间内的最大行宽（避开头部与手臂下垂）。
    band = [sum(row) for row in rows[y0 + int(height * 0.15):
                                     y0 + int(height * 0.32)]]
    shoulder = max(band) if band else 0
    rgb = list(im.convert("RGB").getdata())
    inner = [rgb[i] for i, m in enumerate(mask) if m]
    nw = sum(1 for r, g, b in inner if is_near_white(r, g, b))
    cy = sum(1 for r, g, b in inner if is_cyan(r, g, b))
    hr = sum(1 for r, g, b in inner if is_hot_red(r, g, b))
    return {
        "size": [w, h], "mask_kind": mask_kind,
        "alpha_range": alpha_range, "mask_px": len(inner),
        "bbox": [x0, y0, x1 + 1, y1 + 1], "height_px": height,
        "shoulder_px": shoulder,
        "shoulder_over_height": round(shoulder / height, 5),
        "near_white_ratio": round(nw / len(inner), 6),
        "cyan_ratio": round(cy / len(inner), 6),
        "hot_red_ratio": round(hr / len(inner), 6),
        "near_white_px": nw, "cyan_px": cy, "hot_red_px": hr,
    }


def iou_from_bbox(a: dict, b: dict) -> float:
    """按各自 bbox 归一化到 256 高后的外接框 IoU（上界，不是像素 IoU）。"""
    aw = a["bbox"][2] - a["bbox"][0]
    ah = a["bbox"][3] - a["bbox"][1]
    bw = b["bbox"][2] - b["bbox"][0]
    bh = b["bbox"][3] - b["bbox"][1]
    s = 256 / max(ah, bh)
    ia = aw * s * 256
    ib = bw * s * 256
    inter = min(aw, bw) * s * 256
    return round(inter / (ia + ib - inter), 5)


def main() -> int:
    tex = {k: texture_features(GAME / "assets" / "3d" / name)
           for k, name in TEX.items()}
    sv = {k: silhouette_stats(Image.open(V1 / name))
          for k, name in SV.items()}
    iou = iou_from_bbox(sv["player"], sv["foe"])
    shoulder_delta = abs(sv["player"]["shoulder_over_height"]
                         - sv["foe"]["shoulder_over_height"])
    silhouette_separable = (iou <= 0.60 or shoulder_delta >= 0.15)

    # 板：贴图上把 motif 网格画出来 + 两侧 SV 缩略并排。
    pad, cell, label = 20, 256, 44
    W = pad * 3 + 2 * cell
    H = pad * 3 + cell + 2 * label + 260
    canvas = Image.new("RGB", (W, H), (24, 28, 38))
    d = ImageDraw.Draw(canvas)
    f = ImageFont.truetype(str(FONT), 16) if FONT.is_file() \
        else ImageFont.load_default()
    for i, k in enumerate(("player", "foe")):
        x = pad + i * (cell + pad)
        im = Image.open(GAME / "assets" / "3d" / TEX[k]).convert("RGB")
        canvas.paste(im.resize((cell, cell), Image.LANCZOS), (x, pad))
        g = tex[k]["motif_grid"]
        gmax = max(1, tex[k]["grid_max"])
        for gy in range(GRID):
            for gx in range(GRID):
                v = g[gy][gx] / gmax
                d.rectangle(
                    [x + gx * cell / GRID, pad + gy * cell / GRID,
                     x + (gx + 1) * cell / GRID - 2,
                     pad + (gy + 1) * cell / GRID - 2],
                    outline=(int(60 + 195 * v), int(210 - 130 * v), 90),
                    width=2)
        d.text((x + 4, pad + cell + 6),
               f"{k} · near_white={tex[k]['ratios']['near_white']} "
               f"cyan={tex[k]['ratios']['cyan']}", font=f,
               fill=(200, 210, 230))
        sv_im = Image.open(V1 / SV[k]).convert("RGB")
        sy = pad + cell + label + 8
        canvas.paste(sv_im.resize((130, 160), Image.LANCZOS), (x, sy))
        d.text((x + 136, sy + 6),
               f"mask white={sv[k]['near_white_ratio']}", font=f,
               fill=(200, 210, 230))
        d.text((x + 136, sy + 28),
               f"mask cyan={sv[k]['cyan_ratio']}", font=f,
               fill=(200, 210, 230))
        d.text((x + 136, sy + 50),
               f"shoulder/h={sv[k]['shoulder_over_height']}", font=f,
               fill=(200, 210, 230))
    d.text((pad, H - 34),
           f"bbox-normalized silhouette IoU(upper bound)={iou}  "
           f"shoulder_delta={round(shoulder_delta, 5)}  "
           f"J-01 already satisfied={silhouette_separable}",
           font=f, fill=(230, 200, 130))
    BOARD.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(BOARD)

    checks = {
        "both_textures_4096": all(v["orig_size"] == [4096, 4096]
                                  for v in tex.values()),
        "both_sv_masks_nonempty": all("error" not in v for v in sv.values()),
        "foe_texture_has_no_large_white": (
            tex["foe"]["ratios"]["near_white"] < 0.01),
        "player_texture_has_large_white": (
            tex["player"]["ratios"]["near_white"] > 0.05),
        "board_written": BOARD.is_file() and BOARD.stat().st_size > 50000,
    }
    report = {
        "texture": tex, "subviewport_v1": sv,
        "silhouette": {"bbox_iou_upper_bound": iou,
                       "shoulder_delta": round(shoulder_delta, 5),
                       "j01_already_satisfied": silhouette_separable},
        "board": str(BOARD), "board_bytes": BOARD.stat().st_size,
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k, v in tex.items():
        print("TEX", k, v["ratios"], "grid_max", v["grid_max"])
        print("  grid", v["motif_grid"])
    for k, v in sv.items():
        print("SV", k, v["mask_kind"], "mask_px", v["mask_px"],
              "white", v["near_white_ratio"], "cyan", v["cyan_ratio"],
              "hot_red", v["hot_red_ratio"],
              "shoulder/h", v["shoulder_over_height"])
    print("SILHOUETTE iou_upper", iou, "shoulder_delta",
          round(shoulder_delta, 5), "J01", silhouette_separable)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("MOTIF_BASELINE_J_OK" if report["ok"]
          else "MOTIF_BASELINE_J_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
