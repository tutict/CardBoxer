"""A 路线全帧 A/B：A2 连续壳资产 vs C 路线 V2 的权重回传方案。

同帧、同卡、同增益对照，不写死实测数字；阈值由 verify_a.py 用相对口径给。
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
VARIANTS = ("A2_x1", "A2_x15", "V2_V1_base", "V2_V1_gain")
KEYS = ("tear_p999_m", "tear_gt5cm", "max_displacement_m", "moved_gt_1mm",
        "reach_f_m", "reach_b_m", "reach_max_m", "foot_gap_m",
        "penetration_pct")


def agg(vals):
    s = sorted(vals)
    n = len(s)
    return {"min": round(s[0], 5), "mean": round(sum(s) / n, 5),
            "p95": round(s[int(n * 0.95)], 5), "max": round(s[-1], 5)}


def main() -> int:
    d = json.loads((HERE / "a_build.json").read_text(encoding="utf-8"))
    rows = d["all_frames"]["rows"]
    per = {v: {k: agg([r[v][k] for r in rows]) for k in KEYS}
           for v in VARIANTS}

    def r(a, b):
        return round(a / b, 4) if b > 1e-9 else None

    # 同增益 x1.5 的公平对照：A2 定稿 vs V2 定稿
    decomp = {
        "tear_worst_A2x15_over_V2x15": r(per["A2_x15"]["tear_p999_m"]["max"],
                                         per["V2_V1_gain"]["tear_p999_m"]["max"]),
        "tear_mean_A2x15_over_V2x15": r(per["A2_x15"]["tear_p999_m"]["mean"],
                                         per["V2_V1_gain"]["tear_p999_m"]["mean"]),
        "gt5cm_worst_A2x15_over_V2x15": r(per["A2_x15"]["tear_gt5cm"]["max"],
                                           per["V2_V1_gain"]["tear_gt5cm"]["max"]),
        "foot_worst_A2x15_over_V2x15": r(per["A2_x15"]["foot_gap_m"]["max"],
                                          per["V2_V1_gain"]["foot_gap_m"]["max"]),
        "reach_mean_A2x15_over_V2x15": r(per["A2_x15"]["reach_max_m"]["mean"],
                                          per["V2_V1_gain"]["reach_max_m"]["mean"]),
        "reach_mean_A2x15_over_A2x1": r(per["A2_x15"]["reach_max_m"]["mean"],
                                        per["A2_x1"]["reach_max_m"]["mean"]),
    }
    tear_wins = sum(1 for x in rows
                    if x["A2_x15"]["tear_p999_m"] <= x["V2_V1_gain"]["tear_p999_m"])
    foot_wins = sum(1 for x in rows
                    if x["A2_x15"]["foot_gap_m"] <= x["V2_V1_gain"]["foot_gap_m"])
    reach_kept = sum(1 for x in rows
                     if x["A2_x15"]["reach_max_m"]
                     >= x["V2_V1_gain"]["reach_max_m"] * 0.95)

    out = {"frames": len(rows), "cards": d["all_frames"]["cards"],
           "variants": VARIANTS, "per_variant": per,
           "decomposition": decomp,
           "tear_wins_frames": tear_wins, "foot_wins_frames": foot_wins,
           "reach_kept_frames": reach_kept,
           "chain": d["chain"], "reopen": d["reopen"]}
    (HERE / "metrics_a.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"FRAMES={len(rows)}")
    print(f"{'variant':<12} {'tear_mean':>10} {'tear_max':>10} "
          f"{'gt5cm_max':>10} {'foot_max':>10} {'reach_mean':>11} {'pen_max':>9}")
    for v in VARIANTS:
        p = per[v]
        print(f"{v:<12} {p['tear_p999_m']['mean']:>10} "
              f"{p['tear_p999_m']['max']:>10} "
              f"{p['tear_gt5cm']['max']:>10} "
              f"{p['foot_gap_m']['max']:>10} "
              f"{p['reach_max_m']['mean']:>11} "
              f"{p['penetration_pct']['max']:>9}")
    print("DECOMP " + json.dumps(decomp, ensure_ascii=False))
    print(f"TEAR_WINS={tear_wins}/{len(rows)} FOOT_WINS={foot_wins}/{len(rows)} "
          f"REACH_KEPT={reach_kept}/{len(rows)}")
    print("METRICS_A_ANALYZED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
