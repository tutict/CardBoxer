# -*- coding: utf-8 -*-
"""P5 差距诊断（#214）：纯读盘 + 纯计算，不改任何文件。

按 pose_metrics.py 的 13 个指标把 15 轨摆平，标出「有 active 段的攻击轨」
与「无 active 段的位移/受击轨」，并给出 L1~L8 的可复算差距清单。
产出 data/pose_gap.json 与 stdout 摘要。
"""
from __future__ import annotations

import json
from pathlib import Path

from pose_metrics import (
    HERE, GAME, JOINTS, all_metrics, joints_of, load_json,
    peak_pose_distance, phases_of, tracks_of,
)

CM_PATH = GAME / "data" / "card_motion.json"
OUT = HERE / "data" / "pose_gap.json"


def quantile(vals: list, q: float) -> float:
    s = sorted(vals)
    if not s:
        return 0.0
    pos = (len(s) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (pos - lo), 4)


def main() -> None:
    cm = load_json(CM_PATH)
    trs = tracks_of(cm)
    stance = joints_of(cm["stance"])
    met = all_metrics(cm)
    attacks, others = [], []
    for name, (group, tr) in trs.items():
        (attacks if "active" in phases_of(tr) else others).append(name)
    attacks.sort()
    others.sort()

    out = {
        "source": str(CM_PATH),
        "track_count": len(trs),
        "attack_tracks": attacks,
        "other_tracks": others,
        "metrics": met,
        "attack_distribution": {},
        "peak_pair_distances": {},
        "gaps": [],
    }

    numeric = [k for k in ("windup_recoil_px", "windup_hip_drop_px",
                           "peak_reach_gain_px", "peak_bbox_gain_pct",
                           "end_drift_px", "arc_deviation_px",
                           "stance_width_max_px") if k in next(iter(met.values()))]
    for k in numeric:
        vals = [met[n][k] for n in attacks]
        out["attack_distribution"][k] = {
            "min": round(min(vals), 4), "q25": quantile(vals, 0.25),
            "q50": quantile(vals, 0.50), "q75": quantile(vals, 0.75),
            "max": round(max(vals), 4),
        }

    # L8：攻击轨两两峰值姿态距离
    for i, a in enumerate(attacks):
        for b in attacks[i + 1:]:
            out["peak_pair_distances"][f"{a}|{b}"] = peak_pose_distance(cm, a, b)

    gaps = out["gaps"]

    # L3：峰值必须落在 active 段（最硬的一条，可直接判红）
    for n in attacks:
        ph = met[n]["peak_reach_phase"]
        if ph != "active":
            gaps.append({
                "rule": "L3", "track": n, "severity": "hard",
                "detail": f"reach 峰值在 {ph} 段 @frame {met[n]['peak_reach_argmax']}，"
                          f"与命中帧错位",
            })

    # L2：大招/中招/轻招的伸展与剪影强度应随牌型递减
    tiers = {"wave": "triple/heavy", "cross": "sequence/medium",
             "jab": "scatter/light"}
    reach_by_tier = {k: met[k]["peak_reach_gain_px"] for k in tiers}
    if not (reach_by_tier["wave"] > reach_by_tier["cross"] > reach_by_tier["jab"]):
        gaps.append({
            "rule": "L2", "track": "wave/cross/jab", "severity": "hard",
            "detail": f"三档伸展强度未递减: {reach_by_tier}",
        })
    for n in attacks:
        if met[n]["peak_reach_gain_px"] < 5.0:
            gaps.append({
                "rule": "L2", "track": n, "severity": "note",
                "detail": f"峰值前手伸展仅 {met[n]['peak_reach_gain_px']} px"
                          f"（剪影 +{met[n]['peak_bbox_gain_pct']}%）",
            })

    # L4：P4 之后全表无整帧定格；这是「已验收结论」，不是待修 bug
    holds = {n: met[n]["exact_hold_pairs"] for n in met}
    out["exact_hold_total"] = sum(holds.values())
    gaps.append({
        "rule": "L4", "track": "ALL", "severity": "conflict",
        "detail": f"P4 落地后精确平台总数 {sum(holds.values())}；"
                  "招牌动作的 hitstop 不能用「整帧完全相同」实现，"
                  "否则打回 P4 承重判据",
    })

    # L5：末帧漂移红线来自 pose_probe.gd（≤1.5 px）
    worst = max(met.items(), key=lambda kv: kv[1]["end_drift_px"])
    out["end_drift_worst"] = {"track": worst[0], "px": worst[1]["end_drift_px"]}
    gaps.append({
        "rule": "L5", "track": worst[0], "severity": "constraint",
        "detail": f"全表最大起收招漂移 {worst[1]['end_drift_px']} px，"
                  "pose_probe.gd 红线 1.5 px；随动过冲不得推高末帧",
    })

    # L1：起手段有没有「反向预加载」
    for n in attacks:
        if met[n]["windup_recoil_px"] < 1.0 or met[n]["windup_hip_drop_px"] < 1.0:
            gaps.append({
                "rule": "L1", "track": n, "severity": "note",
                "detail": f"蓄力后收 {met[n]['windup_recoil_px']} px / "
                          f"重心下沉 {met[n]['windup_hip_drop_px']} px",
            })

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")

    print("== 轨道分类 ==")
    print(f"attack({len(attacks)}): {attacks}")
    print(f"other ({len(others)}): {others}")
    print("\n== 攻击轨 13 指标 ==")
    keys = list(next(iter(met.values())).keys())
    print("track".ljust(12) + "".join(k[:11].rjust(13) for k in keys))
    for n in attacks + others:
        print(n.ljust(12) + "".join(str(met[n][k])[:11].rjust(13) for k in keys))
    print("\n== 攻击轨分布 ==")
    for k, v in out["attack_distribution"].items():
        print(f"{k:26s} {v}")
    print("\n== 三档伸展 (L2) ==")
    print(reach_by_tier)
    print("\n== 峰值姿态两两距离 (L8) ==")
    for k, v in sorted(out["peak_pair_distances"].items(), key=lambda kv: kv[1]):
        print(f"  {k:24s} {v}")
    print(f"\n== 差距清单 {len(gaps)} 条 ==")
    for g in gaps:
        print(f"  [{g['severity']:10s}] {g['rule']} {g['track']:12s} {g['detail']}")
    print("\n== 红线 ==")
    print(f"exact_hold_total={out['exact_hold_total']} "
          f"end_drift_worst={out['end_drift_worst']}")
    print("WROTE", OUT)


if __name__ == "__main__":
    main()
