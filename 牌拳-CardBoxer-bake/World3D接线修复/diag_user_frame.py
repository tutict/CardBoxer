"""定位用户贴的截图来自哪一张证据图、哪一格（精确逐行像素匹配）。

用户图若是从候选板直接裁剪（未缩放），若干行的 RGB 字节序列会与
候选图某一行的连续子段完全相同，且所有命中行的 y 偏移一致。
这比肉眼比对硬，也不受看图工具缩放影响。

用法：python diag_user_frame.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
USER = Path(r"C:\Users\tutic\.workbuddy\clipboard-images"
            r"\clipboard-2026-11-14T07-41-08-103Z-c0f0d105.png")
OUT = HERE / "data" / "user_frame_origin.json"

CANDS = [
    BAKE / "朝向修复" / "boards" / "朝向-改前改后对照.png",
    BAKE / "B路线-资产层去重" / "boards" / "B-World3D真因对照.png",
    BAKE / "B路线-资产层去重" / "boards" / "B-资产层归因.png",
    HERE / "boards" / "World3D修复-改前改后对照.png",
    HERE / "boards" / "World3D修复-角色亮度对照.png",
    HERE / "shots" / "legacy" / "sh-legacy-live.png",
    HERE / "shots" / "shipped" / "sh-shipped-live.png",
    HERE / "shots" / "world3d_min" / "none" / "min-none-live.png",
    HERE / "shots" / "world3d_min" / "own" / "min-own-live.png",
]


def main() -> int:
    u = Image.open(USER).convert("RGB")
    uw, uh = u.size
    sample_rows = [20, 60, 120, 200, 260]
    sample_rows = [r for r in sample_rows if r < uh]
    needles = {r: u.crop((0, r, uw, r + 1)).tobytes()
               for r in sample_rows}
    results = []
    for c in CANDS:
        if not c.is_file():
            continue
        im = Image.open(c).convert("RGB")
        w, h = im.size
        rec = {"file": str(c), "size": [w, h], "hits": [],
               "matched_rows": 0, "offset_y": None, "offset_x": None}
        if w < uw or h < uh:
            results.append(rec)
            continue
        lines = [im.crop((0, y, w, y + 1)).tobytes() for y in range(h)]
        hits = []
        for sr, needle in needles.items():
            for y, lb in enumerate(lines):
                x = lb.find(needle)
                if x >= 0:
                    hits.append((sr, x, y))
                    break
        rec["hits"] = hits
        offs = Counter(y - sr for sr, x, y in hits)
        xs = Counter(x for sr, x, y in hits)
        if offs:
            (oy, n_off), = offs.most_common(1)
            ox, n_x = xs.most_common(1)[0]
            rec["offset_y"] = oy
            rec["offset_x"] = ox
            rec["matched_rows"] = n_off
            rec["x_agreement"] = n_x
        results.append(rec)

    exact = [r for r in results
             if r["matched_rows"] == len(needles)
             and r["x_agreement"] == len(needles)]
    report = {
        "user_image": str(USER), "user_size": [uw, uh],
        "sample_rows": sample_rows,
        "candidates": results,
        "exact_matches": [r["file"] for r in exact],
        "conclusion": ("逐行像素完全命中" if exact else
                       "未找到未缩放的精确裁剪来源；可能是缩放/重编码过的截图"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("USER", uw, uh, "sample_rows", sample_rows)
    for r in results:
        print("CAND", Path(r["file"]).name, r["size"],
              "matched_rows", r["matched_rows"],
              "offset", r["offset_x"], r["offset_y"])
    print("EXACT", [Path(f).name for f in report["exact_matches"]])
    print(report["conclusion"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
