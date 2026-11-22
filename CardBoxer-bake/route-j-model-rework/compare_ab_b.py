"""B 路线 P2 诊断：量化「B GLB 装上后」与「I 基线 v1」的引擎内像素差。

看图 j-sv-foe.png 里头顶青冠/红花、腿前白布青云纹仍在，
必须先用数字判定是「改动根本没进渲染」还是「改动只在 foe ROI 生效」。
口径沿用 I 路线 visual_diag_i.json：threshold_sum_rgb=18，
player_roi=[361,280,487,545]，foe_roi=[793,280,921,545]。

只读，输出 data/compare_ab_b.json。
用法：python compare_ab_b.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
V1 = HERE / "shots" / "asset_v1"
B = HERE / "shots" / "asset_b"
OUT = HERE / "data" / "compare_ab_b.json"
THRESHOLD = 18
ROIS = {"player": [361, 280, 487, 545],
        "foe": [793, 280, 921, 545]}


def diff(a: Path, b: Path, roi=None) -> dict:
    ia = Image.open(a).convert("RGB")
    ib = Image.open(b).convert("RGB")
    assert ia.size == ib.size, (ia.size, ib.size)
    if roi:
        ia, ib = ia.crop(roi), ib.crop(roi)
    pa, pb = list(ia.getdata()), list(ib.getdata())
    assert len(pa) == len(pb)
    changed = 0
    total_delta = 0
    for (r1, g1, b1), (r2, g2, b2) in zip(pa, pb):
        d = abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2)
        total_delta += d
        if d > THRESHOLD:
            changed += 1
    return {"changed_px": changed, "total_px": len(pa),
            "ratio": round(changed / len(pa), 6),
            "mae": round(total_delta / len(pa), 4)}


def main() -> int:
    both_v1, both_b = V1 / "j-both.png", B / "j-both.png"
    sv_v1, sv_b = V1 / "j-sv-foe.png", B / "j-sv-foe.png"
    result = {
        "threshold_sum_rgb": THRESHOLD,
        "rois": ROIS,
        "both_full": diff(both_v1, both_b),
        "both_player_roi": diff(both_v1, both_b, ROIS["player"]),
        "both_foe_roi": diff(both_v1, both_b, ROIS["foe"]),
        "sv_foe_full": diff(sv_v1, sv_b),
        "files": {
            "v1_both": str(both_v1), "b_both": str(both_b),
            "v1_sv_foe": str(sv_v1), "b_sv_foe": str(sv_b),
        },
    }
    result["verdict"] = (
        "B GLB 在 foe ROI 有显著变化，需进一步看具体部件"
        if result["both_foe_roi"]["ratio"] > 0.05
        else "B GLB 几乎没有改变渲染，疑似未生效或顶点被 skin 拉回")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k in ("both_full", "both_player_roi", "both_foe_roi",
              "sv_foe_full"):
        print("DIFF", k, result[k])
    print("VERDICT", result["verdict"])
    print("COMPARE_AB_B_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
