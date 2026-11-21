"""诊断 b-after-side.png 里那条细长线：属于目标壳（红）还是保留壳（灰）。

Workbench MATERIAL 二色：B_TARGET=(1.0,0.15,0.15)、B_KEEP=(0.62,...)。
若线是红色 ⇒ 塌缩没生效或材质索引错；若是灰色 ⇒ 仍有一个未删的细长壳，
需要按像素 bbox 反查它在 3D 里的位置。
只读，输出 data/after_side_b.json。
用法：python diag_after_side_b.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
IMG = HERE / "shots" / "after_b" / "b-after-side.png"
OUT = HERE / "data" / "after_side_b.json"
# 侧视图里那条线大致位于画面右半、从上到下
STRIP_ROI = (300, 150, 470, 720)


def main() -> int:
    im = Image.open(IMG).convert("RGBA")
    w, h = im.size
    px = list(im.getdata())
    counts = {"red": 0, "gray": 0, "other": 0, "transparent": 0}
    bbox = {"red": [w, h, 0, 0], "gray": [w, h, 0, 0]}
    strip = {"red": 0, "gray": 0, "other": 0}
    for i, (r, g, b, a) in enumerate(px):
        x, y = i % w, i // w
        if a <= 16:
            counts["transparent"] += 1
            continue
        if r > g + 60 and r > b + 60:
            kind = "red"
        elif abs(r - g) < 24 and abs(g - b) < 24:
            kind = "gray"
        else:
            kind = "other"
        counts[kind] += 1
        if kind in bbox:
            q = bbox[kind]
            q[0], q[1] = min(q[0], x), min(q[1], y)
            q[2], q[3] = max(q[2], x), max(q[3], y)
        if STRIP_ROI[0] <= x < STRIP_ROI[2] and \
                STRIP_ROI[1] <= y < STRIP_ROI[3]:
            strip[kind] += 1
    report = {
        "image": str(IMG), "size": [w, h], "strip_roi": list(STRIP_ROI),
        "counts": counts, "bbox": bbox, "strip_counts": strip,
        "verdict": ("red=塌缩残留/材质索引问题" if strip["red"] > 200
                    else "gray=尚有未删的细长保留壳"),
        "ok": True,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("COUNTS", counts)
    print("BBOX", bbox)
    print("STRIP", strip)
    print("VERDICT", report["verdict"])
    print("AFTER_SIDE_DIAG_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
