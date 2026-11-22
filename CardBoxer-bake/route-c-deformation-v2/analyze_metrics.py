"""把 c2_build.json 的 72 帧 × 4 组原始指标汇总成可复算对照表。

不设主观阈值；这里只做聚合与单变量拆解，门禁阈值由 verify_c2.py 用
「相对基线」表述（不写死实测数字）。
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
VARIANTS = ("V1_base", "V1_gain", "V2_base", "V2_final")
KEYS = ("reach_max_m", "reach_f_m", "reach_b_m", "max_delta_deg",
        "tear_p999_m", "tear_gt5cm", "max_displacement_m",
        "foot_gap_m", "penetration_pct", "moved_gt_1mm")


def agg(vals):
    s = sorted(vals)
    n = len(s)
    return {"min": round(s[0], 5), "mean": round(sum(s) / n, 5),
            "p95": round(s[int(n * 0.95)], 5), "max": round(s[-1], 5)}


def ratio(a, b):
    return round(a / b, 4) if b > 1e-9 else None


def main() -> int:
    d = json.loads((HERE / "c2_build.json").read_text(encoding="utf-8"))
    rows = d["all_frames"]["rows"]
    per = {v: {k: agg([r[v][k] for r in rows]) for k in KEYS} for v in VARIANTS}

    # 单变量拆解：只增益 / 只权重 / 两者叠加
    decomp = {
        "gain_only_on_V1": ratio(per["V1_gain"]["reach_max_m"]["mean"],
                                 per["V1_base"]["reach_max_m"]["mean"]),
        "weight_only_at_x1": ratio(per["V2_base"]["reach_max_m"]["mean"],
                                   per["V1_base"]["reach_max_m"]["mean"]),
        "gain_on_V2": ratio(per["V2_final"]["reach_max_m"]["mean"],
                            per["V2_base"]["reach_max_m"]["mean"]),
        "combined_V2_final_over_V1_base": ratio(
            per["V2_final"]["reach_max_m"]["mean"],
            per["V1_base"]["reach_max_m"]["mean"]),
        "tear_worst_V2_final_over_V1_base": ratio(
            per["V2_final"]["tear_p999_m"]["max"],
            per["V1_base"]["tear_p999_m"]["max"]),
        "tear_worst_V2_final_over_rigid_C_baseline": ratio(
            per["V2_final"]["tear_p999_m"]["max"], 0.28048),
    }

    # 逐帧非负：V2_final 的幅度是否每帧都不低于 V1_base
    non_negative = sum(1 for r in rows
                       if r["V2_final"]["reach_max_m"] >= r["V1_base"]["reach_max_m"])
    worst = {
        "tear_p999_m": per["V2_final"]["tear_p999_m"]["max"],
        "tear_gt5cm": per["V2_final"]["tear_gt5cm"]["max"],
        "foot_gap_m": per["V2_final"]["foot_gap_m"]["max"],
        "penetration_pct": per["V2_final"]["penetration_pct"]["max"],
    }
    purities = {
        fam: {"v1": d["weights"]["v1_purity"][fam]["mean_own_weight"],
              "v2": d["weights"]["v2_purity"][fam]["mean_own_weight"],
              "delta": round(d["weights"]["v2_purity"][fam]["mean_own_weight"]
                             - d["weights"]["v1_purity"][fam]["mean_own_weight"], 5)}
        for fam in d["weights"]["v1_purity"]
    }

    out = {"frames": len(rows), "cards": d["all_frames"]["cards"],
           "variants": VARIANTS, "per_variant": per,
           "decomposition": decomp, "purity": purities,
           "reach_non_negative_frames": non_negative,
           "V2_final_worst": worst,
           "stance_identity": d["stance_identity"],
           "assets": d["assets"]}
    (HERE / "metrics_summary.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"FRAMES={len(rows)} PURITY_DELTA=" + json.dumps(
        {k: v["delta"] for k, v in purities.items()}, ensure_ascii=False))
    print(f"{'variant':<10} {'reach_mean':>11} {'reach_max':>10} "
          f"{'tear_p999_max':>15} {'gt5cm_max':>10} {'foot_gap_max':>14} "
          f"{'penetration_max':>17}")
    for v in VARIANTS:
        p = per[v]
        print(f"{v:<10} {p['reach_max_m']['mean']:>11} "
              f"{p['reach_max_m']['max']:>10} "
              f"{p['tear_p999_m']['max']:>15} {p['tear_gt5cm']['max']:>10} "
              f"{p['foot_gap_m']['max']:>14} "
              f"{p['penetration_pct']['max']:>17}")
    print("DECOMP " + json.dumps(decomp, ensure_ascii=False))
    print(f"REACH_NON_NEGATIVE={non_negative}/{len(rows)}")
    print("METRICS_ANALYZED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
