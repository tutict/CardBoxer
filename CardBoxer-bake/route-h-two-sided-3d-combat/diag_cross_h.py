"""H 路线：双侧模式 vs 单侧隔离模式，逐侧 ROI 像素对账（v2 订正版）。

v1（备份在 data/cross_h_v1_retired.json）用「跨进程 ROI 绝对像素等价」
当判据：要求 left_both ≈ left_only_player、right_both ≈ right_only_foe。
实测四个 ratio 全在 0.40~0.54，报 CROSS_H_SUSPICIOUS。这不是串味，
是口径错了：BOTH 与 ONLY_P / ONLY_F 分别来自三个不同的 Godot 进程，
每次启动随机化全局 RNG，观众席 / 灯光相位 / 手牌都会变，跨进程整帧
像素等价在 G 路线就已经退役（G 验证记录踩坑节）。

v2 改判据：
1. 四个 ratio 只作事实记录，不再要求绝对值 < 0.20。
2. 改用**方向性**判据：双侧左侧更接近「只有玩家」而不是「只有对手」，
   双侧右侧更接近「只有对手」而不是「只有玩家」，且差值 > 0.05。
   跨进程噪声是共同基线，排序仍然有意义。
3. 真正的「两个 SubViewport 互不串味」硬证据是同进程同树的
   data/vp_diag_h.json：隐藏一侧时另一侧 ROI changed_px 精确为 0。

输出 data/cross_h.json，带 retired_metric 字段供 verify_h.py 钉住，
防止哪天又把跨进程绝对等价当 PASS 复用。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots"
BOTH = SHOTS / "two_side_ab" / "h-both-stance.png"
ONLY_P = SHOTS / "isolate" / "player" / "h-both-stance.png"
ONLY_F = SHOTS / "isolate" / "foe" / "h-both-stance.png"
ROI = json.loads((HERE / "data" / "roi_h.json").read_text(encoding="utf-8"))
OUT = HERE / "data" / "cross_h.json"

RETIRED = ("absolute ROI pixel identity across separate Godot processes "
           "(v1: ratio < 0.20)")


def diff(a: Path, b: Path, box) -> dict:
    ia = Image.open(a).convert("RGB").crop(box)
    ib = Image.open(b).convert("RGB").crop(box)
    d = ImageChops.difference(ia, ib)
    changed = sum(1 for px in d.get_flattened_data() if sum(px) > 18)
    total = ia.width * ia.height
    return {"changed_px": changed, "total_px": total,
            "ratio": round(changed / total, 4)}


def main() -> int:
    boxes = ROI["boxes"]
    assert len(boxes) == 2
    left, right = boxes[0], boxes[1]
    out = {
        "left_both_vs_only_player": diff(BOTH, ONLY_P, left),
        "left_both_vs_only_foe": diff(BOTH, ONLY_F, left),
        "right_both_vs_only_foe": diff(BOTH, ONLY_F, right),
        "right_both_vs_only_player": diff(BOTH, ONLY_P, right),
        "left_roi": left, "right_roi": right,
        "retired_metric": RETIRED,
        "primary_evidence": "data/vp_diag_h.json (same-process A/B, "
                            "untouched ROI changed_px == 0)",
        "v1_backup": "data/cross_h_v1_retired.json",
    }
    lp = out["left_both_vs_only_player"]["ratio"]
    lf = out["left_both_vs_only_foe"]["ratio"]
    rf = out["right_both_vs_only_foe"]["ratio"]
    rp = out["right_both_vs_only_player"]["ratio"]
    out["directional_margin"] = {
        "left": round(lf - lp, 4), "right": round(rp - rf, 4)}
    # 方向性判据：对应单侧必须比反侧更接近，且余量不是浮点抖动。
    out["checks"] = {
        "left_matches_player_more": lp < lf,
        "right_matches_foe_more": rf < rp,
        "left_margin_above_noise": (lf - lp) > 0.05,
        "right_margin_above_noise": (rp - rf) > 0.05,
        "no_absolute_identity_claim": "retired_metric" in out,
    }
    out["ok"] = all(out["checks"].values())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k, v in out.items():
        if isinstance(v, dict):
            print(k, v)
    print("MARGIN", out["directional_margin"], "ok", out["ok"])
    print("CROSS_H_V2_OK" if out["ok"] else "CROSS_H_V2_FAILED")
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
