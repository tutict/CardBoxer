"""I 路线：定位「玩家 ROI 在 on/plain 之间变化」到底落在哪。

零操作对照已证明同状态逐像素 0，所以这不是抖动。
输出：变化像素的行/列直方图、10×10 热块 top10、变化像素的平均色差，
并画一张放大差分热图 boards/I-玩家侧泄漏热图.png。

诚实口径：本脚本只定位，不粉饰。若机制仍不明，验证记录里写「未定位」。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance

HERE = Path(__file__).resolve().parent
H = HERE.parent / "H路线-双方3D侧面战斗"
SHOTS = HERE / "shots" / "visual_ab"
OUT = HERE / "data" / "player_leak_i.json"
BOARD = HERE / "boards" / "I-玩家侧泄漏热图.png"
THR = 18
ROI = json.loads((H / "data" / "roi_h.json").read_text(
    encoding="utf-8"))["boxes"][0]


def main() -> int:
    a = Image.open(SHOTS / "vis-on.png").convert("RGB").crop(ROI)
    b = Image.open(SHOTS / "vis-plain.png").convert("RGB").crop(ROI)
    d = ImageChops.difference(a, b)
    w, h = a.size
    ap = list(a.get_flattened_data())
    bp = list(b.get_flattened_data())
    dp = list(d.get_flattened_data())
    rows = [0] * h
    cols = [0] * w
    blocks = {}
    deltas = []
    for idx, px in enumerate(dp):
        if sum(px) <= THR:
            continue
        y, x = divmod(idx, w)
        rows[y] += 1
        cols[x] += 1
        key = (y // 10, x // 10)
        blocks[key] = blocks.get(key, 0) + 1
        deltas.append([ap[idx][c] - bp[idx][c] for c in range(3)])
    span = [i for i, v in enumerate(rows) if v > 0]
    cspan = [i for i, v in enumerate(cols) if v > 0]
    mean_delta = ([round(sum(v[c] for v in deltas) / len(deltas), 2)
                   for c in range(3)] if deltas else [0, 0, 0])
    top = sorted(blocks.items(), key=lambda kv: -kv[1])[:10]
    out = {
        "roi": ROI, "size": [w, h], "threshold_sum_rgb": THR,
        "changed_px": len(deltas),
        "changed_ratio": round(len(deltas) / (w * h), 4),
        "mean_delta_on_minus_plain": mean_delta,
        "row_span": [min(span), max(span)] if span else [],
        "col_span": [min(cspan), max(cspan)] if cspan else [],
        "top_10px_blocks": [{"block": [k[1] * 10, k[0] * 10],
                             "changed_px": v} for k, v in top],
        "max_row": max(rows) if rows else 0,
        "max_col": max(cols) if cols else 0,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    # 热图：差分放大 + 原图并列
    z = 3
    heat = ImageEnhance.Brightness(d).enhance(3.0)
    canvas = Image.new("RGB", (2 * w * z + 60, h * z + 60), (20, 24, 34))
    canvas.paste(a.resize((w * z, h * z), Image.LANCZOS), (20, 20))
    canvas.paste(heat.resize((w * z, h * z), Image.LANCZOS),
                 (w * z + 40, 20))
    dr = ImageDraw.Draw(canvas)
    dr.text((20, h * z + 26), "玩家 ROI · on", fill=(160, 225, 205))
    dr.text((w * z + 40, h * z + 26), "差分 ×3（亮 = 变化）",
            fill=(240, 180, 150))
    BOARD.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(BOARD)
    print("CHANGED", out["changed_px"], "RATIO", out["changed_ratio"])
    print("MEAN_DELTA", mean_delta, "ROW_SPAN", out["row_span"],
          "COL_SPAN", out["col_span"])
    print("TOP_BLOCKS", out["top_10px_blocks"][:5])
    print("WROTE", BOARD.name, BOARD.stat().st_size, "B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
