"""P2 阶段二：把真实 GLB 的撕裂扫描汇总成可复算的「幅度增益 vs 撕裂」结论。

阈值在看到结果之前就钉死，来自**外部历史锚**，不按结果调：
  P999_LIMIT_M   = 0.09365  C 路线 7 档全部增益里的最坏 p999
  POSE_ERR_LIMIT = 1e-5     Blender 读回 pose matrix 与解析期望的最大偏差

口径订正（首版判据写错）：曾把 0.28048 m（C 路线**刚性权重的 p999**）
拿去卡本轮的 `max_edge_tear_m`（**单条边最大值**），是拿 p999 与 max
两个不同统计量互比，10 档全红且连线上基线也红。实测本轮单条最大边在
全部 10 档恒为 0.367047 m，与增益无关 ⇒ 既有单边伪影（根位移主导），
不是 P2 引入的。故 `max_edge_tear_m` 降级为 diagnostic_only，另加一条
「跨档恒定」断言把它钉成基线固有量；放行只看 p999 外部锚。

不达标即判不可用；达标只说明「撕裂不是瓶颈」，仍需引擎内看图才能放行。

用法：python analyze_tear_sweep.py
产出：data/tear_sweep.json、boards/P2-real-glb-gain-tearing-tradeoff.png
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
D = HERE / "data"
BOARDS = HERE / "boards"
SRC = D / "tear_sweep_blender.json"
PLAN = D / "sweep_plan.json"
HIST = BAKE / "route-c-real-3d-fix" / "gain_sweep.json"
OUT = D / "tear_sweep.json"
PNG = BOARDS / "P2-real-glb-gain-tearing-tradeoff.png"

P999_LIMIT_M = 0.09365
RIGID_BASELINE_P999_M = 0.28048  # 只作为对照数字记录，不拿来卡 max edge
POSE_ERR_LIMIT = 1e-5


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
    return sum(xs) / len(xs) if xs else 0.0


def main() -> int:
    src = json.loads(SRC.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    hist = json.loads(HIST.read_text(encoding="utf-8"))
    rows = src["rows"]
    cases = {c["id"]: c for c in src["cases"]}
    by_case = {}
    for cid in cases:
        rr = [r for r in rows if r["case"] == cid]
        pp = [p for p in plan["poses"] if p["case"] == cid]
        leg = [max(abs(p["delta_deg"][n]) for n in
                   ("thigh_f", "shin_f", "thigh_b", "shin_b"))
               for p in pp]
        arm = [max(abs(p["delta_deg"][n]) for n in
                   ("upperarm_f", "forearm_f", "upperarm_b", "forearm_b"))
               for p in pp]
        by_case[cid] = {
            "rows": len(rr),
            "worst_p999_m": max(r["p999_edge_tear_m"] for r in rr),
            "mean_p999_m": round(mean([r["p999_edge_tear_m"] for r in rr]), 6),
            "worst_max_edge_m": max(r["max_edge_tear_m"] for r in rr),
            "worst_edges_gt_5cm": max(r["edges_gt_5cm"] for r in rr),
            "total_edges_gt_5cm": sum(r["edges_gt_5cm"] for r in rr),
            "worst_displacement_m": max(r["max_displacement_m"] for r in rr),
            "leg_peak_mean_deg": round(mean(leg), 4),
            "leg_peak_max_deg": round(max(leg), 4),
            "arm_peak_mean_deg": round(mean(arm), 4),
            "arm_peak_max_deg": round(max(arm), 4),
            "max_pose_err": max(r["pose_matrix_max_err"] for r in rr),
        }

    base = by_case["cap03_hard_g100"]
    for cid, row in by_case.items():
        row["leg_amplitude_gain"] = round(
            row["leg_peak_mean_deg"] / max(1e-9, base["leg_peak_mean_deg"]), 4)
        row["p999_over_baseline"] = round(
            row["worst_p999_m"] / max(1e-9, base["worst_p999_m"]), 4)
        row["tear_within_external_anchor"] = (
            row["worst_p999_m"] <= P999_LIMIT_M)
        row["measurement_valid"] = row["max_pose_err"] < POSE_ERR_LIMIT

    max_edge_vals = [r["worst_max_edge_m"] for r in by_case.values()]
    max_edge_constant = (max(max_edge_vals) - min(max_edge_vals)) < 1e-6

    # 只看「候选」档；research（soft）单独列，不参与放行
    usable = sorted(cid for cid, row in by_case.items()
                    if cases[cid]["purpose"] != "research"
                    and row["tear_within_external_anchor"]
                    and row["measurement_valid"])
    verdict = {
        "primary_amplitude_metric": "leg_peak_mean_deg / arm_peak_mean_deg",
        "primary_tear_metric": "p999_edge_tear_m on evaluated player-rigged.glb",
        "external_anchors": {
            "p999_limit_m": P999_LIMIT_M,
            "rigid_baseline_p999_m_for_reference_only": RIGID_BASELINE_P999_M,
            "historical_worst_over_rigid": hist["verdict"]["worst_over_rigid"],
        },
        "baseline_case": "cap03_hard_g100",
        "cases_passing_tear_gate": usable,
        "max_edge_diagnostic_only": {
            "value_m": max(max_edge_vals),
            "constant_across_all_cases": max_edge_constant,
            "reason": ("单条最大边与增益无关、连线上基线也相同，判为既有"
                       "单边伪影（根位移主导）；只作诊断，不作放行判据。"),
        },
        "note": ("达标只说明撕裂不是瓶颈；腿部姿态是否可读、是否出现"
                 "「被削平的平台期」，必须靠引擎内 A/B 截帧看图决定。"),
    }

    checks = {
        "all_poses_evaluated": src["poses_evaluated"] == len(plan["poses"]),
        "all_ten_cases_present": len(cases) == 10,
        "all_cases_have_26_rows": all(r["rows"] == len(plan["frames"])
                                      for r in by_case.values()),
        "edges_match_glb": src["edges"] == 136092,
        "vertices_match_glb": src["vertices"] == 57934,
        "no_missing_bones": src["missing_bones"] == [],
        "pose_matrices_readback_accurate":
            src["max_pose_matrix_err"] < POSE_ERR_LIMIT,
        "max_edge_artifact_is_preexisting": max_edge_constant,
        "shipped_baseline_within_anchor":
            base["worst_p999_m"] <= P999_LIMIT_M,
        "baseline_is_current_shipped_mapping":
            cases["cap03_hard_g100"]["leg_cap_deg"] == 3.0
            and cases["cap03_hard_g100"]["arm_gain_multiplier"] == 1.0,
        "higher_leg_cap_raises_leg_amplitude": all(
            by_case[c]["leg_amplitude_gain"] > 1.0
            for c in ("cap06_hard_g100", "cap09_hard_g100",
                      "cap12_hard_g100")),
        "monotonic_leg_gain": (
            by_case["cap06_hard_g100"]["leg_peak_mean_deg"]
            < by_case["cap09_hard_g100"]["leg_peak_mean_deg"]
            < by_case["cap12_hard_g100"]["leg_peak_mean_deg"]),
        "at_least_one_candidate_passes": len(usable) >= 1,
    }
    report = {"cases": cases, "per_case": by_case, "verdict": verdict,
              "checks": checks, "ok": all(checks.values())}

    # 图：每档 worst p999 柱 + leg 幅度倍率折线
    BOARDS.mkdir(parents=True, exist_ok=True)
    ids = [c["id"] for c in src["cases"]]
    W, H = 1180, 620
    im = Image.new("RGB", (W, H), (22, 22, 28))
    d = ImageDraw.Draw(im)
    f26, f15, f13 = font(26), font(15), font(13)
    d.text((20, 14), "P2 · 游戏真实 GLB：候选增益 vs 边撕裂",
           font=f26, fill=(240, 240, 244))
    d.text((20, 48),
           "左轴/绿柱=p999 最坏边撕裂(m)   右轴/橙线=腿部幅度倍率"
           "   红虚线=左轴历史外部锚 0.09365 m",
           font=f15, fill=(190, 198, 212))
    left, right, top, bot = 70, W - 210, 92, 470
    max_p = max(max(r["worst_p999_m"] for r in by_case.values()),
                P999_LIMIT_M) * 1.15
    h = bot - top
    # 右轴：折线用独立的 0..4 倍率刻度，避免与左轴 p999 混读
    for tick in (0, 1, 2, 3, 4):
        y = bot - h * (tick / 4.0)
        d.line((right, y, right + 6, y), fill=(255, 205, 120), width=1)
        d.text((right + 10, y - 8), f"x{tick}", font=f13,
               fill=(255, 215, 150))
    d.line((left, bot, right, bot), fill=(110, 114, 128), width=2)
    ylim = bot - h * (P999_LIMIT_M / max_p)
    d.line((left, ylim, right, ylim), fill=(220, 90, 90), width=2)
    d.text((right + 8, ylim - 9), "0.09365 m", font=f13,
           fill=(240, 140, 140))
    bw = (right - left) / len(ids)
    pts = []
    for i, cid in enumerate(ids):
        r = by_case[cid]
        x0 = left + i * bw + 8
        x1 = left + (i + 1) * bw - 8
        y = bot - h * (r["worst_p999_m"] / max_p)
        color = (110, 190, 150) if cases[cid]["purpose"] != "research" \
            else (120, 140, 200)
        d.rectangle((x0, y, x1, bot), fill=color)
        d.text((x0, y - 16), f"{r['worst_p999_m']:.4f}", font=f13,
               fill=(215, 222, 232))
        d.text((x0 - 2, bot + 8), cid.replace("_", "\n"), font=f13,
               fill=(190, 198, 212))
        pts.append(((x0 + x1) / 2,
                    bot - h * min(1.0, r["leg_amplitude_gain"] / 4.0)))
    for a, b in zip(pts, pts[1:]):
        d.line((a, b), fill=(255, 205, 120), width=3)
    for i, (x, y) in enumerate(pts):
        d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(255, 220, 150))
        d.text((x + 6, y - 14), f"x{by_case[ids[i]]['leg_amplitude_gain']:.2f}",
               font=f13, fill=(255, 220, 150))
    d.text((20, H - 92),
           "本图只回答「撕裂有没有失控」；腿姿态是否可读由 Godot 内 A/B 截帧判定。",
           font=f15, fill=(210, 216, 226))
    d.text((20, H - 62),
           f"网格 {src['vertices']} 顶点 / {src['edges']} 边；"
           f"姿态矩阵最大读回误差 {src['max_pose_matrix_err']:.2g}。",
           font=f15, fill=(170, 182, 198))
    d.text((20, H - 34),
           "蓝柱=soft 软压缩研究对照（需要改驱动源码，本轮未采纳）；绿柱=纯数据层候选。",
           font=f15, fill=(170, 182, 198))
    im.save(PNG)

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for cid in ids:
        r = by_case[cid]
        print("CASE", cid, "worst_p999", r["worst_p999_m"],
              "max_edge", r["worst_max_edge_m"],
              "gt5cm", r["worst_edges_gt_5cm"],
              "leg_gain", r["leg_amplitude_gain"],
              "pass", r["tear_within_external_anchor"])
    print("PASSING", usable)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("TEAR_SWEEP_OK" if report["ok"] else "TEAR_SWEEP_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
