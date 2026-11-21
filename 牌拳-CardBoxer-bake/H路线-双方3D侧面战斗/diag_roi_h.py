"""H 路线：用 off vs both-stance 的逐列差异自动定位两个 3D 角色的 x 区间。

肉眼按缩放后的预览图估 ROI 会偏（1280 原图被缩到约 1080 显示），
所以这里不猜坐标：逐列数差异像素，找出两段连续峰。
输出 data/roi_h.json 供 make_zoom_h.py 与 verify_h.py 使用。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots" / "two_side_ab"
OFF = SHOTS / "h-off.png"
ON = SHOTS / "h-both-stance.png"
OUT = HERE / "data" / "roi_h.json"
Y0, Y1 = 280, 545


def main() -> int:
    a = Image.open(OFF).convert("RGB").crop((0, Y0, 1280, Y1))
    b = Image.open(ON).convert("RGB").crop((0, Y0, 1280, Y1))
    d = ImageChops.difference(a, b)
    cols = []
    for x in range(1280):
        col = d.crop((x, 0, x + 1, Y1 - Y0))
        cols.append(sum(1 for px in col.get_flattened_data()
                        if sum(px) > 18))
    # 阈值 = 峰值的 12%，把连续段合并（允许 12 px 空洞）
    peak = max(cols)
    thr = max(6, int(peak * 0.12))
    hot = [c > thr for c in cols]
    segs = []
    start = None
    for x, v in enumerate(hot):
        if v and start is None:
            start = x
        if not v and start is not None:
            segs.append([start, x])
            start = None
    if start is not None:
        segs.append([start, 1280])
    merged = []
    for s in segs:
        if merged and s[0] - merged[-1][1] <= 12:
            merged[-1][1] = s[1]
        else:
            merged.append(list(s))
    big = [s for s in merged if s[1] - s[0] >= 40]
    boxes = [[s[0], Y0, s[1], Y1] for s in big[:2]]
    report = {"peak_col_diff": peak, "threshold": thr,
              "segments": big, "boxes": boxes,
              "two_regions": len(boxes) == 2,
              "left_box": boxes[0] if boxes else None,
              "right_box": boxes[1] if len(boxes) > 1 else None}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("PEAK", peak, "THR", thr, "SEGMENTS", big)
    print("BOXES", boxes, "two_regions", report["two_regions"])
    print("ROI_H_OK" if report["two_regions"] else "ROI_H_FAILED")
    return 0 if report["two_regions"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
