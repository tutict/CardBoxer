"""P2 全量复核：15 轨 284 帧 × 3 档在真实 GLB 上的最坏边撕裂。

代表帧 sweep 可能漏掉最坏帧，这里逐帧扫一遍再放行。阈值仍是看结果前
钉死的历史外部锚 0.09365 m（C 路线 7 档最坏 p999），不按结果调。

用法：python analyze_full_tear.py
产出：data/full_tear.json
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = HERE / "data"
SRC = D / "full_tear_blender.json"
PLAN = D / "full_plan.json"
REP = D / "tear_sweep.json"
OUT = D / "full_tear.json"
P999_LIMIT_M = 0.09365
POSE_ERR_LIMIT = 1e-5


def mean(xs) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def main() -> int:
    src = json.loads(SRC.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    rep = json.loads(REP.read_text(encoding="utf-8"))
    rows = src["rows"]
    case_ids = [c["id"] for c in src["cases"]]
    per = {}
    for cid in case_ids:
        rr = [r for r in rows if r["case"] == cid]
        worst = max(rr, key=lambda r: r["p999_edge_tear_m"])
        per[cid] = {
            "frames": len(rr),
            "worst_p999_m": worst["p999_edge_tear_m"],
            "worst_frame": [worst["card"], worst["frame"]],
            "mean_p999_m": round(mean([r["p999_edge_tear_m"]
                                       for r in rr]), 6),
            "frames_over_anchor": sum(1 for r in rr
                                      if r["p999_edge_tear_m"]
                                      > P999_LIMIT_M),
            "worst_edges_gt_5cm": max(r["edges_gt_5cm"] for r in rr),
            "total_edges_gt_5cm": sum(r["edges_gt_5cm"] for r in rr),
            "worst_max_edge_m": max(r["max_edge_tear_m"] for r in rr),
            "worst_displacement_m": max(r["max_displacement_m"] for r in rr),
            "max_pose_err": max(r["pose_matrix_max_err"] for r in rr),
        }
    base = per["cap03_hard_g100"]["worst_p999_m"]
    for cid in case_ids:
        per[cid]["worst_over_shipped_baseline"] = round(
            per[cid]["worst_p999_m"] / base, 4)

    # 代表帧 sweep 是否漏掉更坏的帧
    rep_worst = {cid: rep["per_case"][cid]["worst_p999_m"]
                 for cid in case_ids}
    sampling_gap = {cid: round(per[cid]["worst_p999_m"] - rep_worst[cid], 6)
                    for cid in case_ids}

    expected_pairs = {(f["card"], f["frame"]) for f in plan["frames"]}
    checks = {
        "all_852_poses_evaluated": src["poses_evaluated"] == 852,
        "three_cases": len(case_ids) == 3,
        "each_case_284_frames": all(per[c]["frames"] == 284
                                    for c in case_ids),
        "all_frame_pairs_covered": all(
            {(r["card"], r["frame"]) for r in rows if r["case"] == cid}
            == expected_pairs for cid in case_ids),
        "full_frame_pairs_count": len(expected_pairs) == 284,
        "pose_matrices_readback_accurate":
            src["max_pose_matrix_err"] < POSE_ERR_LIMIT,
        "shipped_baseline_within_anchor":
            per["cap03_hard_g100"]["frames_over_anchor"] == 0,
        "cap09_all_frames_within_anchor":
            per["cap09_hard_g100"]["frames_over_anchor"] == 0
            and per["cap09_hard_g100"]["worst_p999_m"] <= P999_LIMIT_M,
        "cap12_all_frames_within_anchor":
            per["cap12_hard_g100"]["frames_over_anchor"] == 0
            and per["cap12_hard_g100"]["worst_p999_m"] <= P999_LIMIT_M,
        "cap09_worse_than_baseline_only_mildly":
            per["cap09_hard_g100"]["worst_over_shipped_baseline"] < 1.5,
        "cap12_worse_than_baseline_only_mildly":
            per["cap12_hard_g100"]["worst_over_shipped_baseline"] < 1.5,
    }
    report = {
        "anchor_p999_m": P999_LIMIT_M,
        "per_case": per,
        "representative_sweep_worst": rep_worst,
        "sampling_gap_m": sampling_gap,
        "verdict": {
            "full_284_frame_gate": "PASS" if all(checks.values()) else "FAIL",
            "note": ("全量通过只说明撕裂不是瓶颈；最终幅度档仍以引擎内"
                     "A/B 看图的可读性为准。"),
        },
        "checks": checks, "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for cid in case_ids:
        p = per[cid]
        print("CASE", cid, "frames", p["frames"],
              "worst_p999", p["worst_p999_m"], "at", p["worst_frame"],
              "over_anchor", p["frames_over_anchor"],
              "over_baseline", p["worst_over_shipped_baseline"],
              "gt5cm", p["worst_edges_gt_5cm"])
    print("SAMPLING_GAP", sampling_gap)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("FULL_TEAR_OK" if report["ok"] else "FULL_TEAR_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
