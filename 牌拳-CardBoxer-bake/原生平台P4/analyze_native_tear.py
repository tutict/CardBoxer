"""P4 · 全量 284 帧真实 GLB 撕裂汇总（纯读盘）。

阈值在看结果之前钉死，沿用 P2 / P3 的外部历史锚，不按本轮结果调：
  P999_LIMIT_M   = 0.09365   C 路线 7 档增益里的最坏 p999
  POSE_ERR_LIMIT = 1e-5      Blender pose matrix 读回误差上限

强对账：baseline 档是「原动作表 + P3 上线态 atan12」，与 P3 全量扫描
的 atan12 完全同口径，worst_p999 必须逐值相等；不相等说明本轮 plan
构造偏了，而不是「结果有点浮动」。

产出：data/native_tear.json、boards/P4-全量撕裂权衡.png
用法：python analyze_native_tear.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
D = HERE / "data"
BOARDS = HERE / "boards"
SRC = D / "full_tear_blender.json"
PLAN = D / "native_plan.json"
SCAN = D / "candidate_scan.json"
P3_TEAR = BAKE / "方波平台期" / "data" / "plateau_tear.json"
P2_PLAN = BAKE / "动作表现P2" / "data" / "sweep_plan.json"
OUT = D / "native_tear.json"
PNG = BOARDS / "P4-全量撕裂权衡.png"

P999_LIMIT_M = 0.09365
POSE_ERR_LIMIT = 1e-5
CASE_TO_SCAN = {"baseline": "micro_0", "hybrid": "hybrid_lerp_micro03",
                "micro05": "micro_0.5"}
BG = (22, 22, 28)
FG = (230, 234, 242)
MUTED = (180, 190, 206)
ORANGE = (255, 186, 92)
GREEN = (110, 190, 150)
RED = (214, 108, 108)
BLUE = (116, 166, 224)


def font(sz: int):
    for p in (r"C:\Windows\Fonts\msyh.ttc",
              r"C:\Windows\Fonts\simhei.ttf"):
        if Path(p).is_file():
            try:
                return ImageFont.truetype(p, sz)
            except OSError:
                pass
    return ImageFont.load_default()


def mean(xs) -> float:
    return round(sum(xs) / len(xs), 4) if xs else 0.0


def board(per: dict, p3_value: float, base_value: float) -> None:
    W, H = 1400, 720
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    f26, f15, f13, f12 = font(26), font(15), font(13), font(12)
    d.text((20, 10), "P4 · 数据层改法：全量 284 帧真实 GLB 撕裂成本",
           font=f26, fill=FG)
    d.text((20, 48),
           "三档 × 284 帧 = 852 姿态；红虚线是外部锚 0.09365 m，"
           "灰虚线是 P3 上线态 atan12 实测 0.042737 m",
           font=f15, fill=MUTED)
    left, right, top, bot = 110, 1340, 130, 430
    vmax = 0.10
    d.line((left, bot, right, bot), fill=(110, 114, 128), width=2)
    for i in range(5):
        tick = vmax * i / 4
        y = bot - (bot - top) * i / 4
        d.line((left, y, right, y), fill=(52, 56, 66), width=1)
        d.text((left - 88, y - 9), f"{tick:.4f} m", font=f12, fill=MUTED)
    y_anchor = bot - (bot - top) * P999_LIMIT_M / vmax
    d.line((left, y_anchor, right, y_anchor), fill=RED, width=2)
    d.text((right - 260, y_anchor - 20), "外部锚 0.09365 m",
           font=f13, fill=RED)
    y_p3 = bot - (bot - top) * p3_value / vmax
    d.line((left, y_p3, right, y_p3), fill=MUTED, width=1)
    labels = [("baseline（P3 上线态）", GREEN),
              ("hybrid（推荐）", ORANGE), ("micro05（风险对照）", BLUE)]
    slot = (right - left) / 3
    for i, (cid, color) in enumerate(
            [("baseline", GREEN), ("hybrid", ORANGE),
             ("micro05", BLUE)]):
        cx = left + slot * (i + 0.5)
        v = per[cid]["worst_p999_m"]
        h = (bot - top) * v / vmax
        bw = 150
        d.rectangle((cx - bw / 2, bot - h, cx + bw / 2, bot), fill=color)
        d.text((cx - 46, bot - h + 8), f"{v:.6f}", font=f13, fill=BG)
        d.text((cx - 90, bot + 12), labels[i][0], font=f13, fill=FG)
        d.text((cx - 80, bot + 36),
               f"越锚帧 {per[cid]['frames_over_anchor']} / 284",
               font=f12, fill=MUTED)
    d.text((20, 486),
           f"baseline 与 P3 的 atan12 逐值相等："
           f"{base_value:.6f} vs {p3_value:.6f}"
           f"（差 {abs(base_value - p3_value):.2e} m）。",
           font=f15, fill=FG)
    d.text((20, 518),
           "改数据层会重算 13 骨 delta，所以必须重跑全量而非沿用 P3 结论；"
           "三档都不得越锚。",
           font=f15, fill=MUTED)
    d.text((20, 552),
           "平台收益见 P4-候选改法权衡板：hybrid 精确 0 / 可辨 120"
           "（现状 255 / 308）。",
           font=f15, fill=MUTED)
    d.text((20, 596),
           "max_edge_tear_m 跨档恒定，是既有单边伪影，按 P2 口径"
           "降级为 diagnostic_only，不作放行线。",
           font=f13, fill=MUTED)
    d.text((20, 630),
           "姿态 plan 由 make_native_plan.py 生成，"
           "Blender 只消费 delta_deg / root_m，不重算公式。",
           font=f13, fill=MUTED)
    d.text((20, 674),
           "推荐档仍需引擎内 A/B 与 15 套全量自检；成本账不等于放行。",
           font=f13, fill=ORANGE)
    BOARDS.mkdir(parents=True, exist_ok=True)
    im.save(PNG)


def main() -> int:
    src = json.loads(SRC.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    scan = json.loads(SCAN.read_text(encoding="utf-8"))
    p3 = json.loads(P3_TEAR.read_text(encoding="utf-8"))
    p2plan = json.loads(P2_PLAN.read_text(encoding="utf-8"))
    rep_pairs = {(f["card"], f["frame"]) for f in p2plan["frames"]}
    rows = src["rows"]
    cases = {c["id"]: c for c in src["cases"]}
    per, gap = {}, {}
    for cid in cases:
        rr = [r for r in rows if r["case"] == cid]
        rep = [r for r in rr if (r["card"], r["frame"]) in rep_pairs]
        worst = max(r["p999_edge_tear_m"] for r in rr)
        rep_worst = max((r["p999_edge_tear_m"] for r in rep), default=0.0)
        gap[cid] = round(worst - rep_worst, 6)
        peaks = [r["leg_peak_deg"] for r in rr]
        srow = scan["rows"][CASE_TO_SCAN[cid]]
        per[cid] = {
            "frames": len(rr), "representative_frames": len(rep),
            "worst_p999_m": round(worst, 6),
            "representative_worst_p999_m": round(rep_worst, 6),
            "mean_p999_m": mean([r["p999_edge_tear_m"] for r in rr]),
            "frames_over_anchor": sum(
                r["p999_edge_tear_m"] > P999_LIMIT_M for r in rr),
            "worst_max_edge_m": max(r["max_edge_tear_m"] for r in rr),
            "worst_edges_gt_5cm": max(r["edges_gt_5cm"] for r in rr),
            "total_edges_gt_5cm": sum(r["edges_gt_5cm"] for r in rr),
            "leg_peak_mean_deg": mean(peaks),
            "leg_peak_max_deg": round(max(peaks), 4),
            "max_pose_err": max(r["pose_matrix_max_err"] for r in rr),
            "exact_flat_pairs": srow["exact_flat_pairs"],
            "perceptual_flat_pairs": srow["perceptual_flat_pairs"],
            "max_joint_delta_px": srow["max_joint_delta_px"],
        }
        per[cid]["p999_over_baseline"] = round(
            worst / per["baseline"]["worst_p999_m"], 4)
        per[cid]["tear_within_external_anchor"] = worst <= P999_LIMIT_M
    p3_value = p3["per_case"]["atan12"]["worst_p999_m"]
    base_value = per["baseline"]["worst_p999_m"]
    checks = {
        "poses_852": (src["poses_evaluated"] == 852
                      and len(rows) == 852),
        "three_cases_284_each": (len(cases) == 3
                                 and all(v["frames"] == 284
                                         for v in per.values())),
        "plan_frame_pairs_match": (
            len(plan["frames"]) == 284
            and {(f["card"], f["frame"]) for f in plan["frames"]}
            == {(r["card"], r["frame"]) for r in rows
                if r["case"] == "baseline"}),
        "glb_mesh_shape": (src["vertices"] == 57934
                           and src["edges"] == 136092
                           and src["armature_bones"] == 14
                           and src["missing_bones"] == []),
        "pose_matrices_readback_accurate": (
            src["max_pose_matrix_err"] < POSE_ERR_LIMIT),
        "baseline_matches_p3_atan12": abs(base_value - p3_value) < 1e-6,
        "all_cases_within_anchor": all(
            v["tear_within_external_anchor"] for v in per.values()),
        "all_cases_no_frame_over_anchor": all(
            v["frames_over_anchor"] == 0 for v in per.values()),
        "representative_never_worse_than_full": all(
            v >= -1e-9 for v in gap.values()),
        "hybrid_reaches_zero_exact": (
            per["hybrid"]["exact_flat_pairs"] == 0),
        "hybrid_perceptual_below_baseline": (
            per["hybrid"]["perceptual_flat_pairs"]
            < per["baseline"]["perceptual_flat_pairs"]),
        "max_edge_artifact_constant_diagnostic_only": (
            len({round(v["worst_max_edge_m"], 6) for v in per.values()})
            == 1),
    }
    report = {
        "source": {"tear": str(SRC), "plan": str(PLAN),
                   "scan": str(SCAN), "p3_tear": str(P3_TEAR)},
        "anchor_p999_m": P999_LIMIT_M,
        "pose_err_limit": POSE_ERR_LIMIT,
        "p3_atan12_worst_p999_m": p3_value,
        "baseline_worst_p999_m": base_value,
        "poses_evaluated": src["poses_evaluated"],
        "blender": src["blender"],
        "max_pose_matrix_err": src["max_pose_matrix_err"],
        "per_case": per, "sampling_gap_m": gap,
        "recommended_case": "hybrid",
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    board(per, p3_value, base_value)
    for cid, v in per.items():
        print(f"{cid:<10} worst_p999={v['worst_p999_m']:.6f} "
              f"over={v['frames_over_anchor']} "
              f"exact={v['exact_flat_pairs']} "
              f"perc={v['perceptual_flat_pairs']} "
              f"maxpx={v['max_joint_delta_px']}")
    print("P3_ATAN12", p3_value, "P4_BASELINE", base_value)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("NATIVE_TEAR_OK" if report["ok"] else "NATIVE_TEAR_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
