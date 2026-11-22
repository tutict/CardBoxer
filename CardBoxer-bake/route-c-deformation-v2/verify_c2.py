"""C 路线 V2 承重判据：22 条，全部从盘上产物复算，不读「应该是什么」的注释。

设计纪律：
  · 关键倍率一律「汇总表 vs 逐帧 rows 双算」，两边不一致就是真信号；
  · 阈值尽量相对（C 路线刚性基线 / V1_base 最坏值），不写死实测数字；
  · 三条负结果也要被判据钉住，防止后来者把证伪过的方案重新捡起来；
  · 源码级守卫写「赋值 / 调用形态」，不写裸标识符（散文会满足裸子串）。
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
C_ROUTE = BAKE / "route-c-real-3d-fix"

CHECKS = []
VARIANTS = ("V1_base", "V1_gain", "V2_base", "V2_final")


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def expect(name: str, ok: bool, detail: str):
    CHECKS.append({"name": name, "ok": bool(ok), "detail": detail})


def mean(rows, variant, key):
    return sum(r[variant][key] for r in rows) / len(rows)


def worst(rows, variant, key):
    return max(r[variant][key] for r in rows)


def main() -> int:
    base = load(HERE / "baseline.json")
    report = load(HERE / "c2_build.json")
    summary = load(HERE / "metrics_summary.json")
    tmetrics = load(HERE / "territory_metrics.json")
    shells = load(HERE / "shells_probe.json")
    smooth = load(HERE / "smooth_sweep.json")
    croute = load(C_ROUTE / "c_build.json")
    rows = report["all_frames"]["rows"]

    # --- A. 输入与零污染 --------------------------------------------------
    drift = [k for k, m in base["inputs"].items()
             if not (BAKE / m["path"]).is_file()
             or sha256(BAKE / m["path"]) != m["sha256"]]
    expect("V2-01_baseline_inputs_intact", not drift,
           f"checked={len(base['inputs'])} drift={drift}")

    gdrift = [k for k, m in base["game"].items()
              if not (GAME / k).is_file() or sha256(GAME / k) != m["sha256"]]
    expect("V2-02_game_source_unchanged", not gdrift,
           f"checked={len(base['game'])} drift={gdrift}")

    a = report["assets"]
    cov = report["weights"]["covered"] / report["weights"]["verts"]
    expect("V2-03_assets_preserved",
           a["uv_same"] and a["textures_same"] and a["uv_layers"] == 1
           and len(a["textures"]) == 3 and cov > 0.999,
           f"uv={a['uv_layers']} tex={len(a['textures'])} same="
           f"{a['uv_same']}/{a['textures_same']} coverage={cov:.5f}")

    si = report["stance_identity"]
    expect("V2-04_stance_identity",
           si["vertices_identical"] and si["max_vertex_delta_m"] < 1e-5,
           f"max_delta_m={si['max_vertex_delta_m']}")

    # --- B. 全 72 帧变形质量门禁 ------------------------------------------
    cards = report["all_frames"]["cards"]
    shape_ok = (len(rows) == 72 and cards == {"jab": 14, "cross": 22, "wave": 36}
                and all(all(v in r for v in VARIANTS) for r in rows))
    expect("V2-05_frame_count_and_variants", shape_ok,
           f"rows={len(rows)} cards={cards}")

    ratio_recalc = mean(rows, "V1_gain", "reach_max_m") / mean(rows, "V1_base", "reach_max_m")
    ratio_summary = summary["decomposition"]["gain_only_on_V1"]
    expect("V2-06_reach_ratio_double_computed",
           abs(ratio_recalc - ratio_summary) < 0.002 and ratio_recalc > 1.3,
           f"rows={ratio_recalc:.4f} summary={ratio_summary} threshold>1.3")

    nn = sum(1 for r in rows
             if r["V1_gain"]["reach_max_m"] >= r["V1_base"]["reach_max_m"])
    expect("V2-07_reach_non_negative_every_frame",
           nn == len(rows) and nn == summary["reach_non_negative_frames"],
           f"non_negative={nn}/{len(rows)} summary={summary['reach_non_negative_frames']}")

    fg, fb = worst(rows, "V1_gain", "foot_gap_m"), worst(rows, "V1_base", "foot_gap_m")
    expect("V2-08_foot_grounded_all_frames",
           fg <= fb * 1.05 + 1e-9 and fg < 0.05,
           f"worst_gain={fg} worst_base={fb} cap=0.05m")

    pen = worst(rows, "V1_gain", "penetration_pct")
    expect("V2-09_no_torso_penetration", pen == 0.0,
           f"worst_penetration_pct={pen}")

    rigid = croute["jab8_ab"]["rigid_tear"]["p999_edge_tear_m"]
    tg, tb = worst(rows, "V1_gain", "tear_p999_m"), worst(rows, "V1_base", "tear_p999_m")
    expect("V2-10_tear_below_rigid_half", tg < rigid * 0.5,
           f"worst_gain={tg} rigid_C_baseline={rigid} cap={rigid*0.5:.5f}")
    expect("V2-11_tear_gain_cost_bounded", tg <= tb * 2.0,
           f"worst_gain={tg} worst_base={tb} cap=x2.0")

    # 前摇/收招帧本来就是站架（关键帧板 reach=0.0000），不能要求 72 帧全动。
    # 判「确实在动」用活跃帧数下限 + 峰值，而不是 min。
    active = sum(1 for r in rows if r["V1_gain"]["moved_gt_1mm"] > 60000)
    moved_max = max(r["V1_gain"]["moved_gt_1mm"] for r in rows)
    expect("V2-12_mesh_really_moves", active >= 30 and moved_max > 60000,
           f"active_frames={active}/{len(rows)} max_moved_gt_1mm={moved_max}")

    # --- C. 三条负结果必须被如实钉住 --------------------------------------
    wo_recalc = mean(rows, "V2_base", "reach_max_m") / mean(rows, "V1_base", "reach_max_m")
    wo_summary = summary["decomposition"]["weight_only_at_x1"]
    expect("V2-13_territory_no_reach_gain",
           abs(wo_recalc - wo_summary) < 0.002 and 0.99 <= wo_recalc <= 1.01,
           f"rows={wo_recalc:.4f} summary={wo_summary} (purity up, reach flat)")

    tv2, tv1 = worst(rows, "V2_final", "tear_p999_m"), tg
    expect("V2-14_territory_tear_regression",
           tv2 > tv1 * 1.5 and tv2 > tmetrics["per_variant"]["V1_gain"]["tear_p999_m"]["max"] * 1.5,
           f"V2_final_worst={tv2} V1_gain_worst={tv1} ratio={tv2/tv1:.3f}")

    p1, p2 = report["weights"]["v1_purity"], report["weights"]["v2_purity"]
    fams_ok = all(p2[f]["mean_own_weight"] > p1[f]["mean_own_weight"] for f in p1)
    expect("V2-15_territory_purity_did_improve", fams_ok,
           f"families={len(p1)} deltas="
           + json.dumps({f: round(p2[f]["mean_own_weight"] - p1[f]["mean_own_weight"], 5)
                         for f in p1}, ensure_ascii=False))

    sm = shells["small"]
    expect("V2-16_shells_small_holds_body",
           sm["vert_pct"] > 0.9 and sm["shells"] > 2000
           and shells["largest_shell_verts"] < 2000,
           f"small_shells={sm['shells']} vert_pct={sm['vert_pct']} "
           f"largest_shell={shells['largest_shell_verts']}")

    sweep = smooth["results"]
    ref = next(r for r in sweep if r["lam"] == 0.0 and r["iters"] == 0)
    others = [r for r in sweep if not (r["lam"] == 0.0 and r["iters"] == 0)]
    sweep_ok = all(
        r["tear_gain_mean"] >= ref["tear_gain_mean"] * 0.9
        and abs(r["reach_gain_mean"] - ref["reach_gain_mean"])
        / ref["reach_gain_mean"] < 0.01
        for r in others
    )
    expect("V2-17_smooth_sweep_no_real_improvement", sweep_ok,
           f"baseline_tear={ref['tear_gain_mean']} others="
           + json.dumps([r["tear_gain_mean"] for r in others]))

    evidence = [
        "territory_probe.json", "territory_metrics.json",
        "frames/shells-small-only.png",
        "frames/jab07-V1.png", "frames/jab07-V2.png",
        "frames/cross11-V1.png", "frames/cross11-V2.png",
        "frames/wave18-V1.png", "frames/wave18-V2.png",
    ]
    ev_bad = [p for p in evidence
              if not (HERE / p).is_file() or (HERE / p).stat().st_size < 500]
    expect("V2-18_negative_evidence_saved", not ev_bad,
           f"checked={len(evidence)} missing_or_tiny={ev_bad}")

    # --- D. 定稿图与源码接线 ----------------------------------------------
    by_shot = defaultdict(set)
    shot_bad = []
    for s in report["shots"]:
        p = HERE / "frames" / s["file"]
        if not p.is_file() or p.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n" \
                or sha256(p) != s["sha256"] or s["bytes"] < 10000:
            shot_bad.append(s["file"])
        by_shot[s["shot"]].add(s["tag"])
    pairs_ok = all(t == {"A_x1", "B_x15"}
                   for k, t in by_shot.items() if k != "stance-angle55")
    expect("V2-19_final_shots_single_variable",
           not shot_bad and len(report["shots"]) == 21 and pairs_ok
           and len(by_shot) == 11,
           f"shots={len(report['shots'])} groups={len(by_shot)} bad={shot_bad}")

    from PIL import Image
    boards = ["V2-final-comparison-board.png", "V2-keyframe-board.png"]
    board_bad = []
    for name in boards:
        p = HERE / name
        if not p.is_file() or p.stat().st_size < 50000:
            board_bad.append(name)
            continue
        with Image.open(p) as im:
            if im.width < 800 or im.height < 1000:
                board_bad.append(name)
    expect("V2-20_boards_nonblank", not board_bad,
           f"boards={boards} bad={board_bad}")

    src = (HERE / "c2_build.py").read_text(encoding="utf-8")
    params = report["params"]
    nums = {
        "arm_only_gain": float(re.search(r"^ARM_GAIN\s*=\s*([\d.]+)", src, re.M).group(1)),
        "alpha_cross_family": float(re.search(r"^ALPHA\s*=\s*([\d.]+)", src, re.M).group(1)),
        "beta_bridge": float(re.search(r"^BETA\s*=\s*([\d.]+)", src, re.M).group(1)),
    }
    expect("V2-21_params_match_source",
           all(abs(params[k] - v) < 1e-9 for k, v in nums.items()),
           f"report={ {k: params[k] for k in nums} } source={nums}")

    needles = [
        ("import c_build as C", src),
        ('row["V2_final"] = row.pop("V2_gain")', src),
        ('pairs = (("A_x1", v1, base_mapping), ("B_x15", v1, mapping_gain))', src),
        ("C.pose_frame(rig, P, table, stance, None, 0, mapping_gain)", src),
        ("def smooth(", (HERE / "probe_smooth.py").read_text(encoding="utf-8")),
        ("union(e.vertices[0], e.vertices[1])",
         (HERE / "probe_shells.py").read_text(encoding="utf-8")),
    ]
    miss = [n for n, text in needles if n not in text]
    expect("V2-22_source_wiring", not miss,
           f"needles={len(needles)} missing={miss}")

    passed = sum(c["ok"] for c in CHECKS)
    failed = [c["name"] for c in CHECKS if not c["ok"]]
    (HERE / "verify_c2_result.json").write_text(
        json.dumps({"checks": CHECKS, "total": len(CHECKS),
                    "passed": passed, "failed": failed},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for c in CHECKS:
        print(f"{'OK  ' if c['ok'] else 'FAIL'} {c['name']} | {c['detail']}")
    print(f"TOTAL={len(CHECKS)} PASSED={passed} FAILED={failed}")
    print("C2_VERIFIED" if passed == len(CHECKS) else "C2_VERIFY_FAILED")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
