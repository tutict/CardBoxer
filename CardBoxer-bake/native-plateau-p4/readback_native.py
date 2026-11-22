"""P4 · 落地后的独立读回复核（不信 apply 的 ok 字段）。

从**改后的三份表**重新读盘，用 evaluate_candidates.py 的同一套口径复算
精确 / 可辨平台、2D 关节位移，并与改动前的候选扫描逐字段对账；再逐值
核对 landing_tracks.json 的 320 个 edits 是否真的全部写进去了。

用法：python readback_native.py
产出：data/readback_native.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "CardBoxer"
D = HERE / "data"
ORIG = HERE / "orig" / "pre-p4"
DIAG = BAKE / "motion-diagnostics"
sys.path.insert(0, str(DIAG))
sys.path.insert(0, str(HERE))
from evaluate_candidates import Ctx, frame_joints, measure  # noqa: E402

OUT = D / "readback_native.json"


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def tracks_of(d: dict) -> dict:
    out = {k: v["track"] for k, v in d["cards"].items()}
    out.update({k: v["track"] for k, v in d.get("motions", {}).items()})
    return out


def joints_map(d: dict, keys: list[str]) -> dict:
    return {card: [frame_joints(f, keys) for f in tr]
            for card, tr in tracks_of(d).items()}


def main() -> int:
    cm = load(GAME / "data" / "card_motion.json")
    mi = load(GAME / "data" / "motion_input.json")
    mif = load(GAME / "data" / "motion_input_foe.json")
    cm0 = load(ORIG / "card_motion.json")
    mi0 = load(ORIG / "motion_input.json")
    mif0 = load(ORIG / "motion_input_foe.json")
    scan = load(D / "candidate_scan.json")
    landing = load(D / "landing_tracks.json")
    apply_rep = load(D / "apply_native.json")

    keys = list(mi["joint_names"])
    ctx = Ctx(mi)
    orig = joints_map(cm0, keys)
    shipped = joints_map(cm, keys)
    per = {card: measure(ctx, orig[card], shipped[card])
           for card in shipped}
    agg = {
        "exact_flat_pairs": sum(p["exact_flat_pairs"] for p in per.values()),
        "perceptual_flat_pairs": sum(
            p["perceptual_flat_pairs"] for p in per.values()),
        "changed_frames": sum(p["changed_frames"] for p in per.values()),
        "max_joint_delta_px": max(
            p["max_joint_delta_px"] for p in per.values()),
        "max_adjacent_jump_px": max(
            p["max_adjacent_jump_px"] for p in per.values()),
        "baseline_max_adjacent_jump_px": max(
            p["baseline_max_adjacent_jump_px"] for p in per.values()),
    }
    scan_row = scan["rows"]["micro_2"]
    baseline_row = scan["rows"]["micro_0"]

    # 三份表 11 关节同步（改后）
    jm = {"card_motion.json": shipped,
          "motion_input.json": joints_map(mi, keys),
          "motion_input_foe.json": joints_map(mif, keys)}
    sync = {
        "mi_vs_cm": jm["motion_input.json"] == shipped,
        "mi_vs_mif": (jm["motion_input.json"]
                      == jm["motion_input_foe.json"]),
    }

    # 320 个 edits 逐值读回
    edits = landing["edits"]
    edit_total = 0
    edit_bad = []
    for name, obj in (("card_motion.json", cm),
                      ("motion_input.json", mi),
                      ("motion_input_foe.json", mif)):
        trs = tracks_of(obj)
        for card, frames in edits.items():
            for i_s, vals in frames.items():
                for joint, xy in vals.items():
                    edit_total += 1
                    got = trs[card][int(i_s)][joint]
                    if [float(got[0]), float(got[1])] != [
                            float(xy[0]), float(xy[1])]:
                        edit_bad.append((name, card, i_s, joint))

    # 起手/收招归位帧必须与改前逐值相同（pose_probe 1.5 px 红线的数值面）
    endpoint_bad = []
    for name, obj, obj0 in (("card_motion.json", cm, cm0),
                            ("motion_input.json", mi, mi0),
                            ("motion_input_foe.json", mif, mif0)):
        t, t0 = tracks_of(obj), tracks_of(obj0)
        for card in t:
            for idx in (0, len(t[card]) - 1):
                a = {k: tuple(float(x) for x in t[card][idx][k])
                     for k in keys}
                b = {k: tuple(float(x) for x in t0[card][idx][k])
                     for k in keys}
                if a != b:
                    endpoint_bad.append((name, card, idx))

    # 非编辑字段逐值不变（顶层键 + 每帧非腿关节键）
    LEG_JOINTS = set(landing["leg_joints"])
    meta_bad = []
    for name, obj, obj0 in (("card_motion.json", cm, cm0),
                            ("motion_input.json", mi, mi0),
                            ("motion_input_foe.json", mif, mif0)):
        if set(obj) != set(obj0):
            meta_bad.append((name, "root_keys"))
        t, t0 = tracks_of(obj), tracks_of(obj0)
        for card in t:
            if len(t[card]) != len(t0[card]):
                meta_bad.append((name, card, "len"))
                continue
            for i, (f, f0) in enumerate(zip(t[card], t0[card])):
                if set(f) != set(f0):
                    meta_bad.append((name, card, i, "frame_keys"))
                    continue
                for k in f:
                    if k in LEG_JOINTS:
                        continue
                    if f[k] != f0[k]:
                        meta_bad.append((name, card, i, k))
        for k in obj0:
            if k in ("cards", "motions"):
                continue
            if obj.get(k) != obj0[k]:
                meta_bad.append((name, k))

    checks = {
        "fifteen_tracks_284_frames": (
            len(shipped) == 15
            and sum(len(v) for v in shipped.values()) == 284),
        "exact_flat_pairs_zero": agg["exact_flat_pairs"] == 0,
        "perceptual_below_baseline": (
            agg["perceptual_flat_pairs"]
            < baseline_row["perceptual_flat_pairs"]),
        "agg_matches_landing_recomputed": all(
            agg[k] == landing["measure_recomputed"][k] for k in agg),
        "changed_frames_matches_landing": agg["changed_frames"]
        == landing["changed_frame_total"],
        "all_track_endpoints_identical_to_orig": not endpoint_bad,
        "max_displacement_under_2px": agg["max_joint_delta_px"] < 2.0,
        "three_tables_synchronized": all(sync.values()),
        "all_edits_read_back_all_three": (not edit_bad
                                    and edit_total
                                    == 3 * apply_rep["edit_count_per_file"]),
        "non_leg_metadata_unchanged": not meta_bad,
        "apply_report_ok": (
            bool(apply_rep.get("checks"))
            and all(v is True for v in apply_rep["checks"].values())
            and not apply_rep.get("failed")),
    }
    report = {
        "source": "改后读盘 + orig/pre-p4 原字节备份",
        "agg": agg,
        "scan_micro_2": {k: scan_row[k] for k in agg},
        "scan_baseline": {k: baseline_row[k] for k in agg},
        "sync": sync,
        "edit_total_checked": edit_total,
        "edit_mismatches": edit_bad[:10],
        "endpoint_mismatches": endpoint_bad[:10],
        "metadata_mismatches": meta_bad[:10],
        "per_card": {k: {"exact": v["exact_flat_pairs"],
                         "perceptual": v["perceptual_flat_pairs"],
                         "changed": v["changed_frames"]}
                     for k, v in per.items()},
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("READBACK", agg)
    print("SCAN    ", {k: scan_row[k] for k in agg})
    print("BASELINE", {k: baseline_row[k] for k in agg})
    print("EDIT_TOTAL", edit_total, "BAD", len(edit_bad),
          "META_BAD", len(meta_bad))
    print("SYNC", sync)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("READBACK_NATIVE_OK" if report["ok"]
          else "READBACK_NATIVE_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
