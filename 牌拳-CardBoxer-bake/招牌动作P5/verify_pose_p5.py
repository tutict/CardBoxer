# -*- coding: utf-8 -*-
"""P5 · 汇总承重判据（#218）。

不信任任何上游产物的 ok 字段：每份报告独立 all(checks.values()) 复核；
关键数字全部从游戏表 / 备份 / 原始 568 行撕裂数据 / PNG 重新算一遍，
再与报告对账。产物 json 只作为「预期值」，不作为「证据」。

看结果前钉死的口径：
  · 三表 6248 关节值同步、jab 与 P4 基线逐值相同（R2）；
  · 改动只在 wave/cross 的四臂关节、端点零漂移、42 帧；
  · mf 阈值 wave≥55 / cross≥25 / wave≥cross+5、攻击峰值全在 active；
  · 13 骨 delta 变化只落在四臂骨；
  · 引擎 A/B 每行 delta / mf / 像素差独立复算，stance/jab 与 reapplied 零差；
  · GLB 568 行重算 p999，仍在外部锚内且余量 ≥ 2× 已耗成本；
  · 其余 11 个受监控文件 sha 不变，四张看板齐备。

用法：python verify_pose_p5.py
产出：data/verify_pose_p5.json
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import p5_readback as RB  # noqa: E402
from pose_axes import axis_metrics, mf  # noqa: E402
from pose_cost import GAME, delta_and_root, joints_of, load  # noqa: E402

DATA = HERE / "data"
BOARDS = HERE / "boards"
SHOTS = HERE / "shots" / "p5"
BAK = HERE / "orig" / "pre-p5"
BASELINE = HERE / "orig" / "基线-规格阶段.json"
OUT = DATA / "verify_pose_p5.json"
ARM_BONES = ("upperarm_f", "forearm_f", "upperarm_b", "forearm_b")


def jload(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8-sig"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else ""


def diff_px(a, b) -> int:
    a, b = Path(a), Path(b)
    if not (a.is_file() and b.is_file()):
        return -1
    ia, ib = Image.open(a).convert("RGBA"), Image.open(b).convert("RGBA")
    if ia.size != ib.size:
        return -1
    d = ImageChops.difference(ia, ib)
    r, g, bl, al = d.split()
    mx = ImageChops.lighter(ImageChops.lighter(r, g),
                            ImageChops.lighter(bl, al))
    return int(mx.point(lambda v: 255 if v > 8 else 0).histogram()[255])


def self_consistent(rep: dict) -> bool:
    """报告自称 ok 不算数：独立把 checks 逐条验一遍。"""
    ck = rep.get("checks")
    if isinstance(ck, dict) and ck:
        return (all(v is True for v in ck.values())
                and not rep.get("failed")
                and rep.get("ok") is True)
    if isinstance(ck, list) and ck:
        return (all(c.get("ok") is True and c.get("rc") == 0 for c in ck)
                and not rep.get("failed")
                and rep.get("ok") is True)
    return False


def delta_change_bones(cm: dict, cm0: dict) -> tuple[set, int]:
    """从两版表逐帧重算 13 骨 delta，返回 (变化骨集合, 帧数)。"""
    a, b = RB.all_tracks(cm), RB.all_tracks(cm0)
    changed, n = set(), 0
    for card, tr in a.items():
        bt = b.get(card, [])
        if len(bt) != len(tr):
            continue
        for i, frame in enumerate(tr):
            n += 1
            dn, _ = delta_and_root(joints_of(frame))
            do, _ = delta_and_root(joints_of(bt[i]))
            for bone, v in dn.items():
                if abs(float(v) - float(do.get(bone, 0.0))) > 1e-6:
                    changed.add(bone)
    return changed, n


def main() -> int:
    cur = {t: load(GAME / t) for t in RB.TABLES}
    old = {t: load(BAK / Path(t).name) for t in RB.TABLES}
    cm, mi, mif = (cur[t] for t in RB.TABLES)
    cm0 = old[RB.TABLES[0]]

    rep_rb = jload(DATA / "p5_readback.json")
    rep_probe = jload(DATA / "p5_probe.json")
    rep_checks = jload(DATA / "all_checks_p5.json")
    rep_apply = jload(DATA / "apply_pose_p5.json")
    rep_tear = jload(DATA / "pose_tear.json")
    rep_scan = jload(DATA / "candidate_scan.json")
    rep_blender = jload(DATA / "pose_tear_blender.json")
    rec = jload(DATA / "recommended_tracks.json")
    spec = jload(HERE / "招牌动作规格.json")

    # --- A. 落盘表独立重算 ---
    checked, disagree, shape_ok, side_frames = RB.sync_check(cm, [mi, mif])
    ref_frames = sum(len(t) for t in RB.all_tracks(cm).values())
    diffs, changed = RB.diff_paths(cm, cm0)
    scope_bad = [d for d in diffs
                 if d["card"] not in RB.EDITABLE_CARDS
                 or d["joint"] not in RB.ARM_JOINTS]
    jab_equal = (RB.cards_tracks(cm).get("jab")
                 == RB.cards_tracks(cm0).get("jab"))
    ep_worst, ep_who = RB.endpoint_gaps(cm, cm0)
    changed_count = sum(len(s) for s in changed.values())
    stance = joints_of(cm["stance"])
    tracks = RB.all_tracks(cm)
    ax = {c: axis_metrics(tracks[c], stance) for c in RB.ATTACK_CARDS}
    mf_direct = {c: round(max(mf(f, stance) for f in tracks[c]), 4)
                 for c in RB.ATTACK_CARDS}
    bones_changed, frames_delta = delta_change_bones(cm, cm0)

    # --- B. A/B 报告独立复核 ---
    rows = rep_probe.get("rows", [])
    mi_now, mi_old = cur[RB.TABLES[1]], old[RB.TABLES[1]]
    mode_table = {"shipped": mi_now, "reapplied": mi_now,
                  "rolled_back": mi_old}

    def exp_delta(card, frame, mode):
        t = mode_table[mode]
        j = (joints_of(t["stance"]) if card == "stance"
             else joints_of(t["cards"][card]["track"][frame]))
        return delta_and_root(j)[0]

    def exp_mf(card, frame, mode):
        t = mode_table[mode]
        if card == "stance":
            return -1.0
        f = t["cards"][card]["track"][frame]
        st = t["stance"]["f_hand"]
        return math.hypot(float(f["f_hand"][0]) - float(st[0]),
                          float(f["f_hand"][1]) - float(st[1]))

    sh_mp = rep_probe.get("shipped_marker_p", "")
    lg_mp = rep_probe.get("legacy_marker_p", "")
    delta_bad, mf_bad, marker_bad, png_missing = [], [], [], []
    for r in rows:
        want = lg_mp if r["mode"] == "rolled_back" else sh_mp
        if r.get("table_marker_player") != want:
            marker_bad.append(r["key"])
        exp = exp_delta(r["card"], r["frame"], r["mode"])
        for side in ("player", "foe"):
            got = r.get(f"{side}_delta", {})
            if not got or max(abs(float(got.get(k, 1e9)) - exp[k])
                              for k in exp) > 1e-3:
                delta_bad.append((r["key"], side))
        if abs(float(r.get("mf_live", -999.0))
               - exp_mf(r["card"], r["frame"], r["mode"])) > 1e-3:
            mf_bad.append(r["key"])
        for side in ("player", "foe"):
            p = Path(r.get(f"{side}_sv", ""))
            if not (p.is_file() and p.stat().st_size > 5000):
                png_missing.append(str(p))

    # 像素差：报告里的每个 key 重新读盘算一遍
    reported = rep_probe.get("diff_px", {})
    recomputed = {}
    for key in reported:
        prefix, cardfr, side = key.split(":")
        mode = prefix.replace("shipped_vs_", "")
        a = next((r.get(f"{side}_sv", "") for r in rows
                  if r["key"] == f"shipped-{cardfr}"), "")
        b = next((r.get(f"{side}_sv", "") for r in rows
                  if r["key"] == f"{mode}-{cardfr}"), "")
        recomputed[key] = diff_px(a, b)
    diff_mismatch = [k for k, v in reported.items()
                     if recomputed.get(k, -999) != v]
    edited_keys = [k for k in recomputed
                   if k.startswith("shipped_vs_rolled_back")
                   and (":wave" in k or ":cross" in k)]
    unchanged_keys = [k for k in recomputed
                      if k.startswith("shipped_vs_rolled_back")
                      and (":stance" in k or ":jab" in k)]
    reapp_keys = [k for k in recomputed
                  if k.startswith("shipped_vs_reapplied")]

    # --- C. GLB 撕裂原始 568 行独立重算 ---
    raw_rows = rep_blender.get("rows", [])
    anchor = float(rep_tear["anchor_p999_m"])
    per_case = {}
    for r in raw_rows:
        c = r["case"]
        per_case.setdefault(c, []).append(r)
    recomputed_tear = {}
    for c, rs in per_case.items():
        recomputed_tear[c] = {
            "poses": len(rs),
            "worst_p999_m": round(max(float(x["p999_edge_tear_m"])
                                     for x in rs), 6),
            "mean_p999_m": round(
                sum(float(x["p999_edge_tear_m"]) for x in rs) / len(rs), 6),
            "frames_over_anchor": sum(
                1 for x in rs if float(x["p999_edge_tear_m"]) > anchor),
        }
    tear_match = (
        recomputed_tear.get("baseline", {}).get("worst_p999_m")
        == rep_tear["baseline"]["worst_p999_m"]
        and recomputed_tear.get("pose_p5", {}).get("worst_p999_m")
        == rep_tear["pose_p5"]["worst_p999_m"]
        and recomputed_tear.get("baseline", {}).get("mean_p999_m")
        == rep_tear["baseline"]["mean_p999_m"]
        and recomputed_tear.get("pose_p5", {}).get("mean_p999_m")
        == rep_tear["pose_p5"]["mean_p999_m"])
    tear_cost = (recomputed_tear["pose_p5"]["worst_p999_m"]
                 - recomputed_tear["baseline"]["worst_p999_m"])
    headroom = anchor - recomputed_tear["pose_p5"]["worst_p999_m"]

    # --- D. 文件 / sha / 看板 ---
    base = jload(BASELINE)
    other = [rel for rel in base["files"] if rel not in RB.TABLES]
    other_bad = [rel for rel in other
                 if sha(GAME / rel) != base["files"][rel]["sha256"]]
    sha_after_ok = all(
        sha(GAME / t) == rep_apply["files"][t]["sha_after"]
        for t in RB.TABLES)
    sha_before_ok = all(
        sha(BAK / Path(t).name) == rep_apply["files"][t]["sha_before"]
        for t in RB.TABLES)
    board_specs = {
        "候选姿态-成本权衡板-R2.png": (1480, 880),
        "P5-引擎AB对照板.png": (1600, 1080),
        "招牌动作-差距对照板.png": (1600, 1000),
        "候选姿态-成本权衡板.png": None,  # R1 负结果归档，只验存在与非空
    }
    boards_ok = True
    for name, size in board_specs.items():
        p = BOARDS / name
        if not (p.is_file() and p.stat().st_size > 30000):
            boards_ok = False
            continue
        if size and Image.open(p).size != size:
            boards_ok = False

    checks = {
        "readback_report_self_consistent": self_consistent(rep_rb),
        "probe_report_self_consistent": self_consistent(rep_probe),
        "tear_report_self_consistent": self_consistent(rep_tear),
        "apply_report_self_consistent": self_consistent(rep_apply),
        "all_checks_15_of_15_independently": (
            self_consistent(rep_checks)
            and len(rep_checks.get("checks", [])) == 15
            and rep_checks.get("passed") == 15
            and rep_checks.get("total") == 15),
        "recommended_case_all_hard_constraints": all(
            c["name"] != rep_scan["recommended"]
            or (c.get("passed") is True and all(c["checks"].values()))
            for c in rep_scan["cases"]),
        "three_tables_6248_sync_independent": (
            shape_ok and checked == 6248 and not disagree),
        "jab_identical_to_baseline_independent": jab_equal,
        "diffs_confined_to_wave_cross_four_arms_independent": (
            bool(diffs) and not scope_bad),
        "endpoints_zero_drift_independent": ep_worst <= 1e-9,
        "changed_frames_42_independent": (
            changed_count == 42 == rec["changed_frame_total"]),
        "mf_thresholds_met_independent": (
            ax["wave"]["mf_peak_px"] >= 55.0
            and ax["cross"]["mf_peak_px"] >= 25.0
            and ax["wave"]["mf_peak_px"] >= ax["cross"]["mf_peak_px"] + 5.0),
        "all_attack_mf_peaks_in_active_independent": all(
            ax[c]["mf_peak_phase"] == "active" for c in RB.ATTACK_CARDS),
        "mf_direct_recompute_matches_axis_metrics": all(
            abs(mf_direct[c] - ax[c]["mf_peak_px"]) <= 1e-3
            for c in RB.ATTACK_CARDS),
        "delta_changes_only_four_arm_bones_independent": (
            frames_delta == ref_frames == 284
            and bones_changed == set(ARM_BONES)),
        "probe_rows_delta_matches_formula_independent": (
            len(rows) == 30 and not delta_bad),
        "probe_rows_mf_matches_formula_independent": not mf_bad,
        "probe_marker_matches_mode_independent": not marker_bad,
        "probe_sv_pngs_all_present_independent": not png_missing,
        "probe_pixel_diffs_recomputed_match_report": (
            len(recomputed) == len(reported) == 40 and not diff_mismatch),
        "edited_pixel_diffs_all_nonzero": (
            len(edited_keys) == 16
            and all(recomputed[k] > 0 for k in edited_keys)),
        "stance_jab_pixels_zero_recomputed": (
            len(unchanged_keys) == 4
            and all(recomputed[k] == 0 for k in unchanged_keys)),
        "reapplied_pixels_zero_recomputed": (
            len(reapp_keys) == 20
            and all(recomputed[k] == 0 for k in reapp_keys)),
        "tear_568_rows_recomputed_match_report": (
            len(raw_rows) == 568 and len(per_case) == 2
            and all(v["poses"] == 284 for v in recomputed_tear.values())
            and tear_match),
        "tear_within_anchor_and_headroom_2x_cost": (
            headroom >= 0 and headroom >= 2.0 * tear_cost
            and all(v["frames_over_anchor"] == 0
                    for v in recomputed_tear.values())),
        "three_table_sha_match_apply_report": sha_after_ok,
        "backup_sha_match_apply_report": sha_before_ok,
        "other_11_watched_files_sha_unchanged": (
            len(other) == 11 and not other_bad),
        "four_boards_present_and_dimensions_ok": boards_ok,
        "spec_json_has_r1_and_r2_revisions": (
            "metric_revision" in spec and "metric_revision_r2" in spec
            and rec["metric_revision"] == "R1+R2"),
    }
    known_debts = [
        {
            "id": "D1",
            "what": "data/apply_pose_p5.json 的 metric_revision 仍为 R1",
            "why": "apply_pose_p5.py 首版把该字段写死成 R1；#218 已改为从 "
                   "recommended_tracks.json 读取，但历史产物按项目约定不回写",
            "proof": "p5_readback.json 证明 jab 逐值不变、mf 峰值是 R2 口径",
            "apply_report_value": rep_apply.get("metric_revision"),
            "recommended_value": rec.get("metric_revision"),
        },
        {
            "id": "D2",
            "what": "boards/候选姿态-成本权衡板.png 展示 R1 首版口径",
            "why": "生成于 R2 之前，写有「三档递减」「只改 54 帧」",
            "proof": "保留为负结果归档；终版为 候选姿态-成本权衡板-R2.png",
        },
    ]
    report = {
        "source": "independent recompute; upstream ok fields not trusted",
        "recomputed": {
            "joint_values_checked": checked,
            "ref_frames": ref_frames,
            "disagreements": len(disagree),
            "diff_count": len(diffs),
            "changed_frame_count": changed_count,
            "endpoint_worst_px": ep_worst,
            "axis_metrics": ax,
            "mf_direct": mf_direct,
            "delta_changed_bones": sorted(bones_changed),
            "delta_frames": frames_delta,
            "probe_rows": len(rows),
            "pixel_keys_recomputed": len(recomputed),
            "diff_mismatches": diff_mismatch[:20],
            "tear_per_case": recomputed_tear,
            "tear_cost_m": round(tear_cost, 6),
            "tear_headroom_m": round(headroom, 6),
        },
        "known_debts": known_debts,
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("RECOMPUTE joint", checked, "disagree", len(disagree),
          "diffs", len(diffs), "frames", changed_count,
          "endpoint", ep_worst)
    print("RECOMPUTE mf", mf_direct)
    print("RECOMPUTE delta bones", sorted(bones_changed),
          "frames", frames_delta)
    print("RECOMPUTE probe rows", len(rows), "delta_bad", len(delta_bad),
          "mf_bad", len(mf_bad), "marker_bad", len(marker_bad),
          "png_missing", len(png_missing))
    print("RECOMPUTE pixel keys", len(recomputed),
          "mismatch", len(diff_mismatch))
    print("RECOMPUTE tear", recomputed_tear,
          "cost", round(tear_cost, 6), "headroom", round(headroom, 6))
    for k, v in checks.items():
        print("CHECK", k, v)
    print("VERIFY_POSE_P5_OK %d/%d" % (sum(checks.values()), len(checks))
          if report["ok"] else "VERIFY_POSE_P5_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
