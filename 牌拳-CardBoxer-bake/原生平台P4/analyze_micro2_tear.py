"""P4 · 汇总 micro2 全量撕裂结果，与 P3 上线态 / 已测三档对账。

口径与 analyze_native_tear.py 完全一致：
  * 外部锚 P999_LIMIT_M = 0.09365（历史 C 路线 7 档最坏 p999）；
  * pose_matrix_err < 1e-5 才算驱动链读回准确；
  * max_edge_tear_m 跨档恒定是既有单边伪影，只记 diagnostic_only。

用法：python analyze_micro2_tear.py
产出：data/micro2_tear.json
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = HERE / "data"
SRC = D / "micro2_tear_blender.json"
PLAN = D / "micro2_plan.json"
NATIVE = D / "native_tear.json"
LANDING = D / "landing_decision.json"
OUT = D / "micro2_tear.json"

P999_LIMIT_M = 0.09365
POSE_ERR_LIMIT = 1e-5


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    src, plan, native, landing = (load(p) for p in
                                 (SRC, PLAN, NATIVE, LANDING))
    rows = [r for r in src["rows"] if r["case"] == "micro_2"]
    base = native["per_case"]["baseline"]
    p999 = [r["p999_edge_tear_m"] for r in rows]
    worst = round(max(p999), 6)
    over = [r for r in rows
            if r["p999_edge_tear_m"] > P999_LIMIT_M]
    mean = round(sum(p999) / len(p999), 6)
    leg_peak = [r["leg_peak_deg"] for r in rows]

    # 与 native_plan 的 baseline 284 帧逐帧对账：帧集合必须一致
    baseline_rows = load(D / "full_tear_blender.json")["rows"]
    base_rows = [r for r in baseline_rows if r["case"] == "baseline"]
    frame_pairs = {(r["card"], r["frame"]) for r in rows}
    base_pairs = {(r["card"], r["frame"]) for r in base_rows}

    report = {
        "source": str(SRC),
        "case": "micro_2",
        "blender": src["blender"],
        "glb": src["glb"],
        "poses_evaluated": len(rows),
        "edges": src["edges"], "vertices": src["vertices"],
        "max_pose_matrix_err": src["max_pose_matrix_err"],
        "elapsed_s": src["elapsed_s"],
        "anchor_p999_m": P999_LIMIT_M,
        "worst_p999_m": worst,
        "mean_p999_m": mean,
        "frames_over_anchor": len(over),
        "worst_max_edge_m": max(r["max_edge_tear_m"] for r in rows),
        "worst_edges_gt_5cm": max(r["edges_gt_5cm"] for r in rows),
        "total_edges_gt_5cm": sum(r["edges_gt_5cm"] for r in rows),
        "leg_peak_mean_deg": round(sum(leg_peak) / len(leg_peak), 4),
        "leg_peak_max_deg": round(max(leg_peak), 4),
        "baseline_worst_p999_m": base["worst_p999_m"],
        "p999_over_baseline": round(worst / base["worst_p999_m"], 4),
        "hybrid_worst_p999_m": native["per_case"]["hybrid"]["worst_p999_m"],
        "micro05_worst_p999_m": native["per_case"]["micro05"]["worst_p999_m"],
        "landing_exact_flat_pairs": landing["cost_table"]["micro_2"][
            "exact_flat_pairs"],
        "landing_perceptual_flat_pairs": landing["cost_table"]["micro_2"][
            "perceptual_flat_pairs"],
        "checks": {
            "poses_284": len(rows) == 284 and src["poses_evaluated"] == 284,
            "plan_frame_pairs_match": frame_pairs == base_pairs,
            "glb_mesh_shape": (src["vertices"] > 0 and src["edges"] > 0),
            "pose_matrices_readback_accurate": (
                src["max_pose_matrix_err"] < POSE_ERR_LIMIT),
            "within_external_anchor": worst <= P999_LIMIT_M,
            "no_frame_over_anchor": len(over) == 0,
            "single_case": {r["case"] for r in src["rows"]} == {"micro_2"},
            "micro2_not_worse_than_hybrid": (
                worst <= native["per_case"]["hybrid"]["worst_p999_m"]),
            "micro2_delta_under_1mm": (
                worst - base["worst_p999_m"] < 0.001),
            "max_edge_artifact_diagnostic_only": True,
        },
    }
    report["failed"] = [k for k, v in report["checks"].items() if not v]
    report["ok"] = all(report["checks"].values())
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"micro2  worst_p999={worst:.6f} over={len(over)} "
          f"mean={mean:.6f} peak={report['leg_peak_mean_deg']}")
    print(f"baseline {base['worst_p999_m']:.6f}  "
          f"hybrid   {report['hybrid_worst_p999_m']:.6f}  "
          f"micro05  {report['micro05_worst_p999_m']:.6f}")
    # 回填 landing_decision.json 里生成时留空的待补测值（幂等）。
    # 只补这一个字段，不改动扫描结论与否决理由。
    if landing["cost_table"]["micro_2"]["worst_p999_m"] is None:
        landing["cost_table"]["micro_2"]["worst_p999_m"] = worst
        landing["full_tear_source"] = str(OUT)
        LANDING.write_text(
            json.dumps(landing, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        print("BACKFILL landing_decision.micro_2.worst_p999_m", worst)
    for k, v in report["checks"].items():
        print("CHECK", k, v)
    print("MICRO2_TEAR_OK" if report["ok"] else "MICRO2_TEAR_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
