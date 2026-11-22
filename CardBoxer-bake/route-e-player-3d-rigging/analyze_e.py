"""E 路线全 72 帧变形质量分析：E_x1 / E_x15 与对手怪 A2_x15 逐帧对照。

所有数字从 e_build.json 现算，不写死；输出 metrics_e.json 供板与判据共用。
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "e_build.json"
OUT = HERE / "metrics_e.json"

KEYS = ("tear_p999_m", "tear_gt5cm", "max_displacement_m",
        "moved_gt_1mm", "reach_f_m", "reach_b_m", "reach_max_m",
        "foot_gap_m", "penetration_pct")


def summarize(rows, tag):
    out = {}
    for k in KEYS:
        vals = [r[tag][k] for r in rows]
        out[k] = {
            "max": round(max(vals), 6),
            "mean": round(statistics.fmean(vals), 6),
            "min": round(min(vals), 6),
        }
    return out


def main() -> int:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    rows = data["all_frames"]["rows"]
    assert len(rows) == 72, len(rows)
    per_tag = {tag: summarize(rows, tag)
               for tag in ("E_x1", "E_x15", "A2_x15_foe")}

    # 逐帧最坏撕裂比与幅度比：E_x15 / A2_x15_foe
    ratios = []
    for r in rows:
        e, a = r["E_x15"], r["A2_x15_foe"]
        denom = max(a["tear_p999_m"], 1e-9)
        ratios.append({
            "card": r["card"], "frame": r["frame"],
            "tear_ratio": round(e["tear_p999_m"] / denom, 5),
            "tear_e": e["tear_p999_m"], "tear_a": a["tear_p999_m"],
            "reach_e": e["reach_max_m"], "reach_a": a["reach_max_m"],
        })
    worst = max(ratios, key=lambda x: x["tear_ratio"])
    e_reach = sum(1 for x in ratios if x["reach_e"] >= x["reach_a"] - 1e-6)
    better_tear = sum(1 for x in ratios if x["tear_ratio"] < 1.0)

    out = {
        "frames": len(rows),
        "cards": data["all_frames"]["cards"],
        "per_tag": per_tag,
        "worst_tear_ratio": worst,
        "frames_e_reach_not_less_than_foe": e_reach,
        "frames_e_tear_lower_than_foe": better_tear,
        "mean_tear_ratio": round(
            statistics.fmean(x["tear_ratio"] for x in ratios), 5),
        "source": str(SRC.name),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for tag in ("E_x1", "E_x15", "A2_x15_foe"):
        s = per_tag[tag]
        print(f"{tag:<12} tear_p999 max={s['tear_p999_m']['max']:.5f} "
              f"mean={s['tear_p999_m']['mean']:.5f} "
              f"gt5cm_max={s['tear_gt5cm']['max']} "
              f"reach_max={s['reach_max_m']['max']:.5f} "
              f"foot_gap_max={s['foot_gap_m']['max']:.5f}")
    print(f"WORST_TEAR_RATIO={worst['tear_ratio']} "
          f"at {worst['card']}#{worst['frame']} "
          f"(E={worst['tear_e']} A={worst['tear_a']})")
    print(f"MEAN_TEAR_RATIO={out['mean_tear_ratio']} "
          f"REACH_NOT_LESS={e_reach}/{len(rows)} "
          f"TEAR_LOWER={better_tear}/{len(rows)}")
    print("METRICS_E_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
