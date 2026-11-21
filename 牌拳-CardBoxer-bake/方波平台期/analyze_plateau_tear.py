"""P3 · 全量 284 帧真实 GLB 撕裂汇总 + 候选推荐（纯读盘）。

阈值在看结果之前钉死，来自 P2 的**外部历史锚**，不按本轮结果调：
  P999_LIMIT_M   = 0.09365   C 路线 7 档增益里的最坏 p999
  POSE_ERR_LIMIT = 1e-5      Blender pose matrix 读回误差上限

P2 的 soft 档只扫过 26 个代表帧；本轮 5 档 × 284 帧 = 1420 姿态全量，
并给出「代表帧最坏 vs 全量最坏」的 gap，确认没有漏掉更坏的帧。

推荐规则（可复算，不按观感挑）：
  ① 精确平台对必须达到原生平台下限（消掉全部 clamp 平台）；
  ② 全量 worst_p999 ≤ 外部锚，且越锚帧数为 0；
  ③ 在以上候选中取「腿峰值均值最接近现状 hard09」的一档
     —— 不让 B 路线刚提上去的幅度回退，也不盲目放大。

产出：data/plateau_tear.json、boards/P3全量284帧-撕裂权衡.png
用法：python analyze_plateau_tear.py
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
PLAN = D / "plateau_plan.json"
DIAG = D / "plateau_diagnosis.json"
P2_SWEEP = BAKE / "动作表现P2" / "data" / "tear_sweep.json"
P2_PLAN = BAKE / "动作表现P2" / "data" / "sweep_plan.json"
OUT = D / "plateau_tear.json"
PNG = BOARDS / "P3全量284帧-撕裂权衡.png"

P999_LIMIT_M = 0.09365
POSE_ERR_LIMIT = 1e-5
CASE_TO_DIAG = {
    "hard09_baseline": "hard09", "atan09": "atan09",
    "atan12": "atan12", "atan15": "atan15", "tanh12": "tanh12",
}


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


def main() -> int:
    src = json.loads(SRC.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    diag = json.loads(DIAG.read_text(encoding="utf-8"))
    p2 = json.loads(P2_SWEEP.read_text(encoding="utf-8"))
    p2plan = json.loads(P2_PLAN.read_text(encoding="utf-8"))
    rows = src["rows"]
    cases = {c["id"]: c for c in src["cases"]}
    rep_pairs = {(f["card"], f["frame"]) for f in p2plan["frames"]}
    native_floor = diag["mappings"]["hard09"][
        "exact_flat_from_native_track"]

    per_case, sampling_gap = {}, {}
    for cid in cases:
        rr = [r for r in rows if r["case"] == cid]
        rep = [r for r in rr
               if (r["card"], r["frame"]) in rep_pairs]
        worst = max(r["p999_edge_tear_m"] for r in rr)
        rep_worst = max((r["p999_edge_tear_m"] for r in rep),
                        default=0.0)
        sampling_gap[cid] = round(worst - rep_worst, 6)
        leg_peaks = [r["leg_peak_deg"] for r in rr]
        per_case[cid] = {
            "frames": len(rr),
            "representative_frames": len(rep),
            "worst_p999_m": worst,
            "representative_worst_p999_m": rep_worst,
            "mean_p999_m": mean([r["p999_edge_tear_m"] for r in rr]),
            "frames_over_anchor": sum(
                r["p999_edge_tear_m"] > P999_LIMIT_M for r in rr),
            "worst_max_edge_m": max(r["max_edge_tear_m"] for r in rr),
            "worst_edges_gt_5cm": max(r["edges_gt_5cm"] for r in rr),
            "total_edges_gt_5cm": sum(r["edges_gt_5cm"] for r in rr),
            "worst_displacement_m": max(
                r["max_displacement_m"] for r in rr),
            "leg_peak_mean_deg": mean(leg_peaks),
            "leg_peak_max_deg": round(max(leg_peaks), 4),
            "max_pose_err": max(r["pose_matrix_max_err"] for r in rr),
            "exact_flat_pairs": diag["mappings"][
                CASE_TO_DIAG[cid]]["exact_flat_pairs"],
            "perceptual_flat_pairs": diag["mappings"][
                CASE_TO_DIAG[cid]]["perceptual_flat_pairs"],
        }
        per_case[cid]["p999_over_baseline"] = round(
            worst / per_case["hard09_baseline"]["worst_p999_m"], 4)
        per_case[cid]["tear_within_external_anchor"] = (
            worst <= P999_LIMIT_M)
        per_case[cid]["platform_at_native_floor"] = (
            per_case[cid]["exact_flat_pairs"] == native_floor)

    passing = sorted(cid for cid, r in per_case.items()
                     if r["tear_within_external_anchor"]
                     and r["frames_over_anchor"] == 0
                     and r["max_pose_err"] < POSE_ERR_LIMIT
                     and cases[cid]["purpose"] != "research")
    eligible = [c for c in passing
                if per_case[c]["platform_at_native_floor"]]
    base_mean = per_case["hard09_baseline"]["leg_peak_mean_deg"]
    recommended = min(
        eligible, key=lambda c: (abs(per_case[c]["leg_peak_mean_deg"]
                                     - base_mean),
                                 per_case[c]["worst_p999_m"])) \
        if eligible else None

    checks = {
        "all_1420_poses_evaluated": src["poses_evaluated"] == 1420
        and len(rows) == 1420,
        "five_cases": len(cases) == 5,
        "each_case_284_frames": all(
            r["frames"] == 284 for r in per_case.values()),
        "glb_mesh_shape": (src["vertices"] == 57934
                           and src["edges"] == 136092
                           and src["armature_bones"] == 14
                           and src["missing_bones"] == []),
        "pose_matrices_readback_accurate":
            src["max_pose_matrix_err"] < POSE_ERR_LIMIT,
        "external_anchor_matches_p2": (
            p2["verdict"]["external_anchors"]["p999_limit_m"]
            == P999_LIMIT_M),
        "baseline_within_anchor":
            per_case["hard09_baseline"]["tear_within_external_anchor"],
        "representative_frames_subset_of_full": all(
            r["representative_frames"] == len(rep_pairs)
            for r in per_case.values()),
        "representative_never_worse_than_full": all(
            v >= -1e-9 for v in sampling_gap.values()),
        "all_candidates_within_anchor": all(
            per_case[c]["tear_within_external_anchor"]
            for c in cases if cases[c]["purpose"] != "research"),
        "all_candidates_no_frame_over_anchor": all(
            per_case[c]["frames_over_anchor"] == 0
            for c in cases if cases[c]["purpose"] != "research"),
        "recommended_is_passing_and_at_platform_floor": (
            recommended is not None
            and recommended in passing
            and per_case[recommended]["platform_at_native_floor"]),
    }
    report = {
        "source": {"tear": str(SRC), "plan": str(PLAN),
                   "diagnosis": str(DIAG)},
        "anchor_p999_m": P999_LIMIT_M,
        "pose_err_limit": POSE_ERR_LIMIT,
        "native_platform_floor": native_floor,
        "poses_evaluated": src["poses_evaluated"],
        "per_case": per_case,
        "sampling_gap_m": sampling_gap,
        "cases_passing_tear_gate": passing,
        "recommendation_rule": ("平台达到原生下限 + 撕裂在外部锚内 "
                                "+ 腿峰值均值最接近现状"),
        "recommended_case": recommended,
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")

    # ── 图：两个独立纵轴面板，避免双轴量纲歧义 ──
    BOARDS.mkdir(parents=True, exist_ok=True)
    W, H = 1180, 720
    im = Image.new("RGB", (W, H), (22, 22, 28))
    d = ImageDraw.Draw(im)
    f26, f15, f13 = font(26), font(15), font(13)
    ids = [c["id"] for c in src["cases"]]
    d.text((20, 12), "P3 · 全量 284 帧真实 GLB：候选映射的撕裂成本与平台消除",
           font=f26, fill=(240, 240, 244))
    d.text((20, 48),
           f"5 档 × 284 帧 = {src['poses_evaluated']} 姿态；"
           f"网格 {src['vertices']} 顶点 / {src['edges']} 边；"
           f"pose 读回误差 {src['max_pose_matrix_err']:.2g}",
           font=f15, fill=(190, 198, 212))
    left, right = 80, W - 40

    # 面板 1：worst p999
    top, bot = 96, 322
    d.text((20, top - 4), "最坏 p999 边撕裂 (m)", font=f15,
           fill=(215, 222, 232))
    # 虚线说明放标题行右侧：首版放在绘图区右侧，会压住末根柱的柱顶数字
    d.text((right - 250, top - 4), "红虚线 = 外部锚 0.09365 m",
           font=f13, fill=(240, 140, 140))
    mx = max(max(r["worst_p999_m"] for r in per_case.values()),
             P999_LIMIT_M) * 1.15
    h = bot - top - 24
    base_y = bot - 24
    d.line((left, base_y, right, base_y), fill=(110, 114, 128), width=2)
    ylim = base_y - h * (P999_LIMIT_M / mx)
    d.line((left, ylim, right, ylim), fill=(220, 90, 90), width=2)
    bw = (right - left) / len(ids)
    for i, cid in enumerate(ids):
        r = per_case[cid]
        x0, x1 = left + i * bw + 10, left + (i + 1) * bw - 10
        y = base_y - h * (r["worst_p999_m"] / mx)
        color = ((110, 190, 150) if cid == recommended else
                 (120, 140, 200) if cases[cid]["purpose"] == "research"
                 else (150, 175, 205))
        d.rectangle((x0, y, x1, base_y), fill=color)
        # 数值画在柱内顶端，避免与面板标题 / 虚线标注抢位置
        d.text((x0 + 6, y + 8), f"{r['worst_p999_m']:.5f}", font=f13,
               fill=(28, 32, 40))
        d.text((x0 - 2, base_y + 6), cid.replace("_", "\n"), font=f13,
               fill=(190, 198, 212))

    # 面板 2：精确平台对
    top2, bot2 = 386, 588
    d.text((20, top2 - 4), "相邻帧精确平台对（越少越好）", font=f15,
           fill=(215, 222, 232))
    d.text((right - 290, top2 - 4),
           f"黄虚线 = 原生平台下限 {native_floor} 对", font=f13,
           fill=(240, 210, 140))
    mx2 = max(r["exact_flat_pairs"] for r in per_case.values()) * 1.15
    h2 = bot2 - top2 - 24
    base2 = bot2 - 24
    d.line((left, base2, right, base2), fill=(110, 114, 128), width=2)
    floor_y = base2 - h2 * (native_floor / mx2)
    d.line((left, floor_y, right, floor_y), fill=(230, 190, 100), width=2)
    for i, cid in enumerate(ids):
        r = per_case[cid]
        x0, x1 = left + i * bw + 10, left + (i + 1) * bw - 10
        y = base2 - h2 * (r["exact_flat_pairs"] / mx2)
        color = ((110, 190, 150) if cid == recommended else
                 (120, 140, 200) if cases[cid]["purpose"] == "research"
                 else (150, 175, 205))
        d.rectangle((x0, y, x1, base2), fill=color)
        d.text((x0 + 6, y + 8), str(r["exact_flat_pairs"]), font=f13,
               fill=(28, 32, 40))
        d.text((x0 - 2, base2 + 6), cid.replace("_", "\n"), font=f13,
               fill=(190, 198, 212))

    d.text((20, 620),
           "绿柱=推荐档，蓝柱=research 对照；黄虚线=动作表原生平台下限，"
           "任何无状态映射都消不掉它。",
           font=f15, fill=(200, 210, 224))
    d.text((20, 648),
           f"推荐 {recommended}：平台 {native_floor} 对（消除全部 clamp 平台），"
           f"全量最坏 p999 {per_case[recommended]['worst_p999_m']:.5f} m。",
           font=f15, fill=(200, 210, 224))
    d.text((20, 676),
           "撕裂达标只说明成本可控；姿态是否可读仍须引擎内 A/B 截帧看图。",
           font=f15, fill=(170, 182, 198))
    im.save(PNG)

    for cid in ids:
        r = per_case[cid]
        print("CASE", cid, "worst_p999", r["worst_p999_m"],
              "over_anchor", r["frames_over_anchor"],
              "gt5cm", r["worst_edges_gt_5cm"],
              "leg_mean", r["leg_peak_mean_deg"],
              "leg_max", r["leg_peak_max_deg"],
              "flat", r["exact_flat_pairs"],
              "gap", sampling_gap[cid])
    print("PASSING", passing)
    print("RECOMMENDED", recommended)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("PLATEAU_TEAR_OK" if report["ok"]
          else "PLATEAU_TEAR_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
