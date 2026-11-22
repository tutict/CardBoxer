# -*- coding: utf-8 -*-
"""P5 落盘态独立读回：#217 开工前提 + #218 承重判据的表层组件。

只从三份游戏表 + orig/pre-p5 备份 + 规格阶段 sha 基线读盘，逐值独立复算，
**不信任任何中间产物 json 的 ok 字段**（apply / candidate_scan / pose_plan
只作交叉核对，不作判据）。

承重口径（看结果前钉死）：
  R1 主强度指标 mf = |f_hand - stance.f_hand|，与 rig_driver.gd 同口径；
  R2 jab 一帧不动（轻拳的「轻」由帧数表达，不由手伸多远表达）；
  改动只允许落在 wave/cross 的四臂关节，端点帧零漂移；
  13 骨 delta 的变化只允许落在四臂骨（腿骨/躯干骨必须逐值相同）；
  三份表 11 关节逐值同步；其余 11 个受监控文件 sha 不变。

产出 data/p5_readback.json。用法：
  python p5_readback.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pose_axes import axis_metrics, mf  # noqa: E402
from pose_cost import (  # noqa: E402
    GAME, JOINTS, delta_and_root, joints_of, load,
)

BAK = HERE / "orig" / "pre-p5"
BASELINE = HERE / "orig" / "spec-baseline.json"
CAND = HERE / "data" / "recommended_tracks.json"
APPLY = HERE / "data" / "apply_pose_p5.json"
OUT = HERE / "data" / "p5_readback.json"

TABLES = (
    "data/card_motion.json",
    "data/motion_input.json",
    "data/motion_input_foe.json",
)
ARM_JOINTS = frozenset(("f_elbow", "f_hand", "b_elbow", "b_hand"))
ARM_BONES = frozenset(("upperarm_f", "forearm_f", "upperarm_b",
                       "forearm_b"))
EDITABLE_CARDS = frozenset(("wave", "cross"))
ATTACK_CARDS = ("wave", "cross", "jab", "sweep", "throw", "uppercut")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def cards_tracks(obj: dict) -> dict:
    return {k: v["track"] for k, v in obj.get("cards", {}).items()}


def all_tracks(obj: dict) -> dict:
    out = cards_tracks(obj)
    out.update({k: v["track"] for k, v in obj.get("motions", {}).items()})
    return out


def sync_check(cm: dict, sides: list[dict]) -> tuple[int, list, bool, int]:
    """三表逐值对账，口径与 probe_tables.py 一致。

    2D 表把 15 轨拆成 12 张 cards + 3 条 motions；两个 3D 表各自是
    一整份 15 轨 cards。所以参照系必须是 all_tracks(cm)，不是 cm.cards，
    且按「关节 tuple」计数（不是按坐标），两侧合计 2*284*11 = 6248。
    """
    ref = all_tracks(cm)
    checked, disagree, shape_ok = 0, [], True
    total_frames = 0
    for side_no, obj in enumerate(sides):
        for card, tr in cards_tracks(obj).items():
            total_frames += len(tr)
            r = ref.get(card)
            if r is None or len(r) != len(tr):
                shape_ok = False
                disagree.append([side_no, card, "len", len(tr),
                                 -1 if r is None else len(r)])
                continue
            for i, (fa, fb) in enumerate(zip(r, tr)):
                ja, jb = joints_of(fa), joints_of(fb)
                for j in JOINTS:
                    checked += 1
                    if ja[j] != jb[j]:
                        disagree.append([side_no, card, i, j])
    return checked, disagree, shape_ok, total_frames


def diff_paths(now: dict, old: dict) -> tuple[list, dict]:
    """返回 (diff 明细, 每卡改动帧集合)；只比关节值，不比元数据。"""
    a, b = all_tracks(now), all_tracks(old)
    rows, changed = [], {}
    for card, tr in a.items():
        old_tr = b.get(card)
        if old_tr is None or len(old_tr) != len(tr):
            rows.append({"card": card, "frame": -1, "joint": "<track>",
                         "axis": -1, "delta": 0.0})
            continue
        for i, (fa, fb) in enumerate(zip(tr, old_tr)):
            for j in JOINTS:
                for ax in (0, 1):
                    d = float(fa[j][ax]) - float(fb[j][ax])
                    if abs(d) > 1e-9:
                        rows.append({"card": card, "frame": i,
                                     "joint": j, "axis": ax,
                                     "delta": round(d, 6)})
                        changed.setdefault(card, set()).add(i)
    return rows, changed


def endpoint_gaps(now: dict, old: dict) -> tuple[float, str]:
    a, b = all_tracks(now), all_tracks(old)
    worst, who = 0.0, "none"
    for card, tr in a.items():
        old_tr = b.get(card, [])
        for label, i in (("first", 0), ("last", len(tr) - 1)):
            if i >= len(old_tr):
                return 1e9, f"{card} {label} missing"
            for j in JOINTS:
                w = max(abs(float(tr[i][j][0]) - float(old_tr[i][j][0])),
                        abs(float(tr[i][j][1]) - float(old_tr[i][j][1])))
                if w > worst:
                    worst, who = w, f"{card} {label} {j}"
    return round(worst, 6), who


def main() -> int:
    cur = {rel: load(GAME / rel) for rel in TABLES}
    old = {rel: load(BAK / Path(rel).name) for rel in TABLES}
    cm, mi, mif = (cur[t] for t in TABLES)
    cm0 = old[TABLES[0]]

    # --- 1. 三表 11 关节逐值同步（参照系 = 2D cards+motions 全 15 轨） ---
    joint_values_checked, disagree, key_ok, side_frames = sync_check(
        cm, [mi, mif])
    ref_frames = sum(len(t) for t in all_tracks(cm).values())
    expected_checked = len(JOINTS) * ref_frames * 2

    # --- 2. 改动范围（2D 真相表 vs P4 上线态备份） ---
    diffs, changed = diff_paths(cm, cm0)
    scope_bad = [d for d in diffs
                 if d["card"] not in EDITABLE_CARDS
                 or d["joint"] not in ARM_JOINTS]
    changed_frames_actual = sorted(
        i for s in changed.values() for i in s)
    changed_frame_count = sum(len(s) for s in changed.values())
    jab_tracks_equal = (
        cards_tracks(cm).get("jab") == cards_tracks(cm0).get("jab"))
    max_2d_delta = max((abs(d["delta"]) for d in diffs), default=0.0)
    ep_worst, ep_who = endpoint_gaps(cm, cm0)

    # --- 3. 元数据 / mapping / 帧结构未变 ---
    cm_meta_now = {k: v for k, v in cm.items()
                   if k not in ("cards", "motions")}
    cm_meta_old = {k: v for k, v in cm0.items()
                   if k not in ("cards", "motions")}
    cm_meta_equal = cm_meta_now == cm_meta_old
    mi_meta_equal = all(
        {k: v for k, v in cur[t].items() if k != "cards"}
        == {k: v for k, v in old[t].items() if k != "cards"}
        for t in TABLES[1:])
    card_shape_equal = all(
        {k: v for k, v in cm["cards"][c].items() if k != "track"}
        == {k: v for k, v in cm0["cards"][c].items() if k != "track"}
        for c in cm["cards"])

    # --- 4. mf 主强度指标（不信任 candidate_scan） ---
    stance = joints_of(cm["stance"])
    stance0 = joints_of(cm0["stance"])
    # 全 15 轨（12 cards + 3 motions）= 3D 表的 284 帧，delta 复算必须用这个
    now_tr = all_tracks(cm)
    old_tr = all_tracks(cm0)
    ax_now = {c: axis_metrics(now_tr[c], stance) for c in ATTACK_CARDS}
    ax_old = {c: axis_metrics(old_tr[c], stance0) for c in ATTACK_CARDS}
    wave_peak = ax_now["wave"]["mf_peak_px"]
    cross_peak = ax_now["cross"]["mf_peak_px"]
    jab_peak = ax_now["jab"]["mf_peak_px"]
    jab_peak_old = ax_old["jab"]["mf_peak_px"]
    active_phases_ok = all(
        ax_now[c]["mf_peak_phase"] == "active" for c in ATTACK_CARDS)
    mf_direct = {c: round(max(mf(f, stance) for f in now_tr[c]), 4)
                 for c in ATTACK_CARDS}

    # --- 5. 13 骨 delta：变化只允许落在四臂骨 ---
    delta_changes: dict[str, int] = {}
    delta_max: dict[str, float] = {}
    non_arm_bad = []
    frames_delta_checked = 0
    for card, tr in now_tr.items():
        old_track = old_tr.get(card, [])
        if len(old_track) != len(tr):
            non_arm_bad.append([card, -1, "track_len"])
            continue
        for i, frame in enumerate(tr):
            d_new, _ = delta_and_root(joints_of(frame))
            d_old, _ = delta_and_root(joints_of(old_track[i]))
            frames_delta_checked += 1
            for bone, val in d_new.items():
                gap = abs(float(val) - float(d_old.get(bone, 0.0)))
                if gap > 1e-6:
                    delta_changes[bone] = delta_changes.get(bone, 0) + 1
                    delta_max[bone] = max(delta_max.get(bone, 0.0), gap)
                    if bone not in ARM_BONES:
                        non_arm_bad.append([card, i, bone, round(gap, 6)])

    # --- 6. 其余受监控文件 sha 未变 ---
    base = json.loads(BASELINE.read_text(encoding="utf-8-sig"))
    watched = base["files"]
    other = [rel for rel in watched if rel not in TABLES]
    other_bad = [rel for rel in other
                 if not (GAME / rel).is_file()
                 or sha(GAME / rel) != watched[rel]["sha256"]]

    # --- 7. 交叉核对（不作判据，只记账） ---
    cand = json.loads(CAND.read_text(encoding="utf-8-sig"))
    apply_rep = json.loads(APPLY.read_text(encoding="utf-8-sig"))
    scan_changed = sum(len(v) for v in cand["changed_frames"].values())
    sha_after_matches = all(
        sha(GAME / t) == apply_rep["files"][t]["sha_after"]
        for t in TABLES)
    sha_before_matches = all(
        sha(BAK / Path(t).name) == apply_rep["files"][t]["sha_before"]
        for t in TABLES)
    # scan 里 jab 是空列表（R2 明确不动），比较时先滤掉空项
    scan_nonempty = {k: sorted(v) for k, v
                     in cand["changed_frames"].items() if v}
    changed_frames_match_scan = (
        {k: sorted(v) for k, v in changed.items()} == scan_nonempty)
    revision_in_apply = apply_rep.get("metric_revision")
    revision_in_cand = cand.get("metric_revision")

    checks = {
        "three_tables_have_same_joint_keys": key_ok,
        # 6248 = 2 侧 * 284 帧 * 11 关节，可复算：len(JOINTS)*ref_frames*2
        "three_tables_6248_joint_values_in_sync": (
            joint_values_checked == expected_checked == 6248
            and side_frames == 2 * ref_frames and not disagree),
        "diffs_exist": len(diffs) > 0,
        "diffs_confined_to_wave_cross_four_arm_joints": not scope_bad,
        "jab_track_byte_for_byte_equivalent_to_baseline": jab_tracks_equal,
        "endpoints_zero_drift": ep_worst <= 1e-9,
        "changed_frame_set_matches_recommended_scan": (
            changed_frames_match_scan),
        "changed_frame_count_matches_scan": (
            changed_frame_count == scan_changed),
        "max_2d_joint_delta_is_design_amplitude": (
            35.0 <= max_2d_delta <= 45.0),
        "card_motion_metadata_unchanged": cm_meta_equal,
        "motion_input_mapping_and_meta_unchanged": mi_meta_equal,
        "card_entry_shape_unchanged": card_shape_equal,
        "wave_mf_peak_at_least_55px": wave_peak >= 55.0,
        "cross_mf_peak_at_least_25px": cross_peak >= 25.0,
        "wave_at_least_5px_stronger_than_cross": (
            wave_peak >= cross_peak + 5.0),
        "jab_mf_peak_unchanged_from_baseline": (
            abs(jab_peak - jab_peak_old) <= 1e-6),
        "all_attack_mf_peaks_in_active": active_phases_ok,
        "delta_changes_only_in_four_arm_bones": (
            not non_arm_bad and set(delta_changes) <= ARM_BONES
            and len(delta_changes) == 4),
        # 284 = 12 cards(228) + 3 motions(56)，从表本身推导，不写死
        "delta_frames_cover_all_3d_frames": (
            frames_delta_checked == ref_frames == 284),
        "other_11_watched_files_sha_unchanged": (
            len(other) == 11 and not other_bad),
    }
    report = {
        "source": "independent readback of shipped tables vs orig/pre-p5",
        "joint_values_checked": joint_values_checked,
        "joint_values_expected": expected_checked,
        "ref_track_frames": ref_frames,
        "side_frames_total": side_frames,
        "joint_value_disagreements": disagree[:20],
        "diff_count": len(diffs),
        "scope_violations": scope_bad[:20],
        "changed_frames": {k: sorted(v) for k, v in changed.items()},
        "changed_frame_count": changed_frame_count,
        "max_2d_joint_delta_px": round(max_2d_delta, 6),
        "endpoint_worst_px": ep_worst,
        "endpoint_where": ep_who,
        "jab_track_equal": jab_tracks_equal,
        "axis_metrics_now": ax_now,
        "axis_metrics_baseline": ax_old,
        "mf_direct_recompute": mf_direct,
        "delta_change_counts_by_bone": delta_changes,
        "delta_max_gap_deg_by_bone": {
            k: round(v, 6) for k, v in delta_max.items()},
        "delta_non_arm_violations": non_arm_bad[:20],
        "delta_frames_checked": frames_delta_checked,
        "other_watched_files": other,
        "other_watched_sha_violations": other_bad,
        "crosscheck": {
            "sha_after_matches_apply_report": sha_after_matches,
            "sha_before_matches_apply_report": sha_before_matches,
            "apply_report_metric_revision": revision_in_apply,
            "recommended_metric_revision": revision_in_cand,
            "note": ("apply_pose_p5.py 硬编码 metric_revision=R1 是元数据债；"
                     "落盘内容由 recommended_tracks.json (R1+R2) 决定，"
                     "以本读回的 jab 零变化 + mf 峰值判据为准"),
        },
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("JOINT_VALUES", joint_values_checked, "DISAGREE", len(disagree))
    print("DIFFS", len(diffs), "SCOPE_BAD", len(scope_bad),
          "CHANGED_FRAMES", changed_frame_count,
          "MAX_2D", round(max_2d_delta, 4))
    print("JAB_EQUAL", jab_tracks_equal, "ENDPOINT", ep_worst, ep_who)
    print("MF_PEAK wave", wave_peak, "cross", cross_peak,
          "jab", jab_peak, "(baseline jab", jab_peak_old, ")")
    print("MF_DIRECT", mf_direct)
    print("DELTA_BONES", delta_changes)
    print("DELTA_NON_ARM_BAD", len(non_arm_bad),
          "FRAMES", frames_delta_checked)
    print("OTHER_WATCHED", len(other), "BAD", len(other_bad))
    for k, v in checks.items():
        print("CHECK", k, v)
    print("P5_READBACK_OK" if report["ok"] else "P5_READBACK_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
