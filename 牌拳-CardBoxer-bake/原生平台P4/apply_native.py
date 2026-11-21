"""P4 · 落地 micro2 数据层改动（可逐字节回退）。

改 3 个文件，且只改四个腿关节在 80 个定格帧上的数值：
  data/card_motion.json        —— 2D 运行时动作表
  data/motion_input.json       —— 玩家侧 3D 运行时动作表
  data/motion_input_foe.json   —— 对手侧 3D 运行时动作表

不做文本 needle 替换：定格段里多帧文本完全相同，needle 不唯一。
改为「load -> 改数值 -> 用同格式 dump」，并在改前证明 round-trip 恒等
（make_landing.py 已实测三份表都逐字节成立）：
  motion_input*.json : json.dumps(separators=(",", ":")) + "\n"，LF
  card_motion.json   : json.dumps(indent=1) 后整体转 CRLF，无尾换行

落地前置：
  * landing_decision.json ok 且 case = micro_2；
  * micro2_tear.json ok（全量 284 帧真实 GLB 撕裂在外部锚内、越锚帧 0）；
  * 三份表 round-trip 恒等。
落地判据：
  * 递归逐值 diff 只允许四个腿关节的坐标路径；
  * 三份表 11 关节仍逐值相同；帧数 / 卡集合 / 非关节元数据全不变；
  * 其余 11 个受监控文件 sha256 不变；
  * --restore 用备份二进制覆盖并 sha256 证明逐字节回退。

用法：python apply_native.py [--restore]
产出：orig/pre-p4/*、data/baseline_p4.json、data/apply_native.json
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "牌拳-CardBoxer"
D = HERE / "data"
ORIG = HERE / "orig" / "pre-p4"
BASE_OUT = D / "baseline_p4.json"
OUT = D / "apply_native.json"

TO_CHANGE = (
    "data/card_motion.json",
    "data/motion_input.json",
    "data/motion_input_foe.json",
)
WATCHED = (
    "scripts/arena.gd", "scripts/fighter_3d_layer.gd",
    "data/motion_input.json", "data/motion_input_foe.json",
    "scripts/fighter.gd", "scripts/rig_driver.gd",
    "scripts/battle_motion_p0.gd", "scripts/battle_rhythm.gd",
    "scripts/card_motion.gd", "scripts/hud.gd",
    "data/card_motion.json", "project.godot",
    "assets/3d/player-rigged.glb", "assets/3d/foe-rigged.glb",
)
LEG_JOINTS = ("f_knee", "f_foot", "b_knee", "b_foot")
DIFF_PAT = re.compile(
    r"^(cards|motions)\.[^.]+\.track\[\d+\]\."
    r"(f_knee|f_foot|b_knee|b_foot)\[\d\]$")


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dumps_for(rel: str, obj: dict) -> bytes:
    if rel == "data/card_motion.json":
        return json.dumps(obj, indent=1, ensure_ascii=False).replace(
            "\n", "\r\n").encode("utf-8")
    return (json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
            + "\n").encode("utf-8")


def diff_paths(a, b, prefix: str = "") -> list[str]:
    if type(a) is not type(b):
        return [prefix or "<root>"]
    if isinstance(a, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            p = f"{prefix}.{k}" if prefix else k
            if k not in a or k not in b:
                out.append(p)
            else:
                out.extend(diff_paths(a[k], b[k], p))
        return out
    if isinstance(a, list):
        if len(a) != len(b):
            return [prefix or "<root>"]
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out.extend(diff_paths(x, y, f"{prefix}[{i}]"))
        return out
    return [] if a == b else [prefix or "<root>"]


def track_of(obj: dict, card: str) -> list:
    if card in obj["cards"]:
        return obj["cards"][card]["track"]
    return obj["motions"][card]["track"]


def all_tracks(obj: dict) -> dict:
    out = {k: v["track"] for k, v in obj["cards"].items()}
    out.update({k: v["track"] for k, v in obj.get("motions", {}).items()})
    return out


def backup_name(rel: str) -> str:
    return Path(rel).name


def report_ok(rep: dict) -> bool:
    ck = rep.get("checks")
    if not isinstance(ck, dict) or not ck:
        return False
    if not all(v is True for v in ck.values()):
        return False
    if rep.get("failed"):
        return False
    return rep.get("ok", True) is True


def do_restore() -> int:
    rows, ok = {}, True
    for rel in TO_CHANGE:
        src, dst = ORIG / backup_name(rel), GAME / rel
        if not src.is_file():
            print("MISSING BACKUP", src)
            return 1
        shutil.copyfile(src, dst)
        rows[rel] = sha(dst) == sha(src)
        ok = ok and rows[rel]
        print("RESTORE", rel, rows[rel])
    print("RESTORE_P4_OK" if ok else "RESTORE_P4_FAILED")
    return 0 if ok else 1


def main() -> int:
    if "--restore" in sys.argv:
        return do_restore()

    # 0) 落地前置：决策 + 全量撕裂都必须真绿
    decision = json.loads((D / "landing_decision.json").read_text(
        encoding="utf-8"))
    tear = json.loads((D / "micro2_tear.json").read_text(encoding="utf-8"))
    landing = json.loads((D / "landing_tracks.json").read_text(
        encoding="utf-8"))
    pre = {
        "landing_decision_ok": report_ok(decision),
        "landing_case_is_micro2": (
            decision.get("decision", "").startswith("落地 micro2")
            and landing.get("case") == "micro_2"),
        "roundtrip_identity_all_three": all(
            decision.get("roundtrip_identity", {}).values()),
        "micro2_full_tear_ok": report_ok(tear),
        "micro2_tear_284_poses": tear.get("poses_evaluated") == 284,
        "micro2_no_frame_over_anchor": tear.get("frames_over_anchor") == 0,
        "micro2_within_external_anchor": (
            tear.get("worst_p999_m", 1e9) <= tear.get("anchor_p999_m", 0)),
    }
    if not all(pre.values()):
        for k, v in pre.items():
            print("PRECHECK", k, v)
        print("APPLY_NATIVE_PRECHECK_FAILED")
        return 1

    ORIG.mkdir(parents=True, exist_ok=True)
    D.mkdir(parents=True, exist_ok=True)

    # 1) 备份 + 14 文件 sha 基线
    for rel in TO_CHANGE:
        shutil.copyfile(GAME / rel, ORIG / backup_name(rel))
    baseline_files = {}
    for rel in WATCHED:
        p = GAME / rel
        baseline_files[rel] = {"exists": p.is_file(),
                               "size": p.stat().st_size if p.is_file() else 0,
                               "sha256": sha(p) if p.is_file() else ""}
    baseline = {
        "game": str(GAME), "to_change": list(TO_CHANGE),
        "files": baseline_files,
        "backups": {r: str(ORIG / backup_name(r)) for r in TO_CHANGE},
        "checks": {
            "all_watched_exist": all(v["exists"]
                                     for v in baseline_files.values()),
            "three_backups_match_live_sha": all(
                sha(ORIG / backup_name(r)) == sha(GAME / r)
                for r in TO_CHANGE),
        },
    }
    baseline["ok"] = all(baseline["checks"].values())
    BASE_OUT.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    edits = landing["edits"]
    keys = list(json.loads((GAME / "data" / "motion_input.json").read_text(
        encoding="utf-8"))["joint_names"])
    edit_count = sum(len(v) for f in edits.values() for v in f.values())

    # 2) 逐文件：round-trip 证明 -> 写数值 -> 同格式 dump -> 落盘
    rows, before_objs, after_objs = {}, {}, {}
    for rel in TO_CHANGE:
        p = GAME / rel
        before_bytes = p.read_bytes()
        before_obj = json.loads(before_bytes.decode("utf-8"))
        after_obj = json.loads(before_bytes.decode("utf-8"))
        rt = dumps_for(rel, before_obj) == before_bytes
        applied = 0
        for card, frames in edits.items():
            tr = track_of(after_obj, card)
            for i_s, vals in frames.items():
                for joint, xy in vals.items():
                    tr[int(i_s)][joint] = list(xy)
                    applied += 1
        after_bytes = dumps_for(rel, after_obj)
        if rt:
            p.write_bytes(after_bytes)
        readback = json.loads(p.read_text(encoding="utf-8"))
        paths = diff_paths(before_obj, readback)
        readback_ok = all(
            track_of(readback, card)[int(i)][j] == list(xy)
            for card, frames in edits.items()
            for i, vals in frames.items()
            for j, xy in vals.items())
        before_objs[rel], after_objs[rel] = before_obj, readback
        rows[rel] = {
            "roundtrip_identity_before": rt,
            "edits_applied": applied,
            "diff_path_count": len(paths),
            "diff_paths_all_leg_joints": all(
                DIFF_PAT.match(x) is not None for x in paths),
            "diff_paths_sample": paths[:6],
            "unexpected_diff_paths": [x for x in paths
                                      if DIFF_PAT.match(x) is None][:6],
            "readback_matches_edits": readback_ok,
            "before_sha256": sha(ORIG / backup_name(rel)),
            "after_sha256": sha(p),
            "before_bytes": len(before_bytes),
            "after_bytes": len(after_bytes),
            "cards": len(all_tracks(readback)),
            "frames": sum(len(t) for t in all_tracks(readback).values()),
        }

    # 3) 三份表 11 关节仍逐值相同
    def joints_map(obj):
        return {
            card: [{k: tuple(float(x) for x in f[k]) for k in keys}
                   for f in tr]
            for card, tr in all_tracks(obj).items()}

    jm = {rel: joints_map(after_objs[rel]) for rel in TO_CHANGE}
    sync = {
        "mi_vs_cm": jm["data/motion_input.json"] == jm["data/card_motion.json"],
        "mi_vs_mif": (jm["data/motion_input.json"]
                      == jm["data/motion_input_foe.json"]),
    }

    # 4) 其余 11 个受监控文件必须逐字节未动
    untouched = {rel: sha(GAME / rel) == baseline_files[rel]["sha256"]
                 for rel in WATCHED if rel not in TO_CHANGE}

    checks = {
        **pre,
        "baseline_ok": baseline["ok"],
        "three_roundtrip_identity_before": all(
            rows[r]["roundtrip_identity_before"] for r in TO_CHANGE),
        "three_edits_applied_all": all(
            rows[r]["edits_applied"] == edit_count for r in TO_CHANGE),
        "three_diff_only_four_leg_joints": all(
            rows[r]["diff_paths_all_leg_joints"] and rows[r]["diff_path_count"] > 0
            for r in TO_CHANGE),
        "three_diff_bounded_by_edits": all(
            rows[r]["diff_path_count"] <= edit_count * 2
            for r in TO_CHANGE),
        "three_readback_matches_edits": all(
            rows[r]["readback_matches_edits"] for r in TO_CHANGE),
        "three_still_15_cards_284_frames": all(
            rows[r]["cards"] == 15 and rows[r]["frames"] == 284
            for r in TO_CHANGE),
        "three_sha_changed": all(
            rows[r]["before_sha256"] != rows[r]["after_sha256"]
            for r in TO_CHANGE),
        "non_joint_metadata_unchanged": all(
            not rows[r]["unexpected_diff_paths"] for r in TO_CHANGE),
        "three_tables_11joints_still_synchronized": all(sync.values()),
        "mapping_unchanged_all_three": all(
            after_objs[r].get("mapping", None)
            == before_objs[r].get("mapping", None) for r in TO_CHANGE),
        "other_watched_files_unchanged": all(untouched.values()),
        "backup_bytes_match_pre_apply": all(
            sha(ORIG / backup_name(r)) == rows[r]["before_sha256"]
            for r in TO_CHANGE),
    }
    report = {
        "mode": "apply", "game": str(GAME), "case": landing["case"],
        "amplitude_px": landing["amplitude_px"],
        "edit_count_per_file": edit_count,
        "changed_frame_total": landing["changed_frame_total"],
        "leg_joints": list(LEG_JOINTS),
        "micro2_worst_p999_m": tear["worst_p999_m"],
        "baseline_worst_p999_m": tear["baseline_worst_p999_m"],
        "rows": rows, "sync": sync, "untouched": untouched,
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("EDITS_PER_FILE", edit_count,
          "CHANGED_FRAMES", landing["changed_frame_total"])
    for r in TO_CHANGE:
        print("TABLE", r, "paths", rows[r]["diff_path_count"],
              "bytes", rows[r]["before_bytes"], "->",
              rows[r]["after_bytes"])
    print("SYNC", sync)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("APPLY_NATIVE_OK" if report["ok"] else "APPLY_NATIVE_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
