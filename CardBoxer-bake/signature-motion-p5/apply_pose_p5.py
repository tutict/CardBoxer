# -*- coding: utf-8 -*-
"""#216 · 把推荐姿态表三表同步落地（可 --restore 逐字节回退）。

沿用 P4 apply_native.py 已验证的做法：load → 改数值 → **同格式 dump**，
并在改前证明 round-trip 恒等；不用文本 needle，不做换行转换。
  card_motion.json   : json.dumps(indent=1) 后整体转 CRLF，无尾换行
  motion_input*.json : json.dumps(separators=(",", ":")) + "\\n"，LF

改动范围钉死：recommended_tracks.json 里 changed_frames 列出的帧，
且只允许 4 个手臂关节（f_hand/f_elbow/b_hand/b_elbow）的 11 关节值变化。
其余字段、其余帧、mapping、 stance、源码、GLB 一律不动。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parent.parent / "CardBoxer"
DATA = GAME / "data"
BACKUP = HERE / "orig" / "pre-p5"
OUT = HERE / "data" / "apply_pose_p5.json"
BASELINE = HERE / "orig" / "spec-baseline.json"

REL = ["data/card_motion.json", "data/motion_input.json",
       "data/motion_input_foe.json"]
JOINTS = ["hip", "shoulder", "head", "f_elbow", "f_hand",
          "b_elbow", "b_hand", "f_knee", "f_foot", "b_knee", "b_foot"]
ARM_JOINTS = {"f_elbow", "f_hand", "b_elbow", "b_hand"}


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(p: Path) -> dict:
    return json.loads(p.read_bytes().decode("utf-8-sig"))


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
        out = []
        for i in range(max(len(a), len(b))):
            p = f"{prefix}[{i}]"
            if i >= len(a) or i >= len(b):
                out.append(p)
            else:
                out.extend(diff_paths(a[i], b[i], p))
        return out
    return [] if a == b else [prefix or "<root>"]


def tracks_of(obj: dict, rel: str) -> dict:
    if rel == "data/card_motion.json":
        out = {k: v["track"] for k, v in obj["cards"].items()}
        out.update({k: v["track"] for k, v in obj["motions"].items()})
        return out
    return {k: v["track"] for k, v in obj["cards"].items()}


def restore() -> int:
    ok = True
    for rel in REL:
        src, dst = BACKUP / Path(rel).name, GAME / rel
        if not src.is_file():
            print("MISSING_BACKUP", src)
            ok = False
            continue
        original = src.read_bytes()
        dst.write_bytes(original)
        same = sha(dst) == hashlib.sha256(original).hexdigest()
        ok &= same
        print("RESTORE", rel, same, sha(dst)[:12])
    print("POSE_P5_RESTORE_OK" if ok else "POSE_P5_RESTORE_FAILED")
    return 0 if ok else 1


def main() -> int:
    if "--restore" in sys.argv:
        return restore()

    rec = load(HERE / "data" / "recommended_tracks.json")
    scan = load(HERE / "data" / "candidate_scan.json")
    expected_changed = next(
        c["changed_frame_total"] for c in scan["cases"]
        if c["name"] == rec["recommended_case"])
    want = rec["tracks"]
    allow = {c: set(v) for c, v in rec["changed_frames"].items()}
    base = load(BASELINE)
    BACKUP.mkdir(parents=True, exist_ok=True)

    # 1) 备份 + 14 文件 sha 基线核对（规格阶段未被改过）
    pre_sha = {}
    for rel in REL:
        p = DATA / Path(rel).name
        b = BACKUP / Path(rel).name
        if not b.is_file():
            shutil.copy2(p, b)
        pre_sha[rel] = sha(p)
        if sha(b) != pre_sha[rel]:
            print("BACKUP_MISMATCH", rel)
            return 1
    baseline_bad = []
    for rel, meta in base["files"].items():
        p = GAME / rel
        if not p.is_file() or sha(p) != meta["sha256"]:
            baseline_bad.append(rel)
    if baseline_bad:
        print("SPEC_STAGE_BASELINE_DRIFT", baseline_bad)
        return 1

    report: dict = {"recommended_case": rec["recommended_case"],
                    # 从推荐档读，别写死：R2 之后产物里残留 "R1" 是元数据债
                    "metric_revision": rec["metric_revision"],
                    "changed_frame_total": rec["changed_frame_total"],
                    "files": {}, "checks": {}}
    changed_paths_total = 0

    # 2) 逐文件 round-trip 证明 → 改数值 → 同格式 dump → 落盘
    for rel in REL:
        p = DATA / Path(rel).name
        raw = p.read_bytes()
        obj = load(p)
        rt = dumps_for(rel, obj)
        if rt != raw:
            print("ROUND_TRIP_NOT_IDENTITY", rel, len(rt), len(raw))
            return 1
        before = json.loads(json.dumps(obj))
        trs = tracks_of(obj, rel)
        missing = [c for c in want if c not in trs]
        if missing:
            print("MISSING_TRACKS", rel, missing)
            return 1
        edits = 0
        for card, frames in want.items():
            dst = trs[card]
            if len(dst) != len(frames):
                print("FRAME_COUNT_MISMATCH", rel, card)
                return 1
            for i, vals in enumerate(frames):
                for k in JOINTS:
                    dst[i][k] = [float(vals[k][0]), float(vals[k][1])]
                    edits += 1
        after_bytes = dumps_for(rel, obj)
        paths = diff_paths(before, obj)
        changed_paths_total += len(paths)
        # 每条改动路径必须落在「允许的帧 × 四个手臂关节 × 坐标 0/1」
        bad = []
        for path in paths:
            parts = path.split(".")
            if len(parts) < 4:
                bad.append(path)
                continue
            leaf_with_idx = parts[-1]
            leaf = leaf_with_idx.split("[")[0]
            if leaf not in ARM_JOINTS or not (
                    leaf_with_idx.endswith("[0]")
                    or leaf_with_idx.endswith("[1]")):
                bad.append(path)
                continue
            track_part = parts[-2]
            card = parts[-3]
            if not track_part.startswith("track["):
                bad.append(path)
                continue
            try:
                idx = int(track_part[6:-1])
            except ValueError:
                bad.append(path)
                continue
            if card not in allow or idx not in allow[card]:
                bad.append(path)
            if leaf not in ARM_JOINTS:
                bad.append(path)
        if bad:
            print("UNEXPECTED_DIFF_PATHS", rel, bad[:10])
            return 1
        p.write_bytes(after_bytes)
        report["files"][rel] = {
            "sha_before": pre_sha[rel], "sha_after": sha(p),
            "bytes_before": len(raw), "bytes_after": len(after_bytes),
            "joint_values_written": edits,
            "diff_path_count": len(paths),
            "round_trip_identity": True,
        }
        print("APPLIED", rel, "edits=%d diff_paths=%d bytes=%d->%d"
              % (edits, len(paths), len(raw), len(after_bytes)))

    # 3) 读回验证：三表 11 关节逐值一致 + 元数据未变 + 其余文件 sha 不变
    live = {rel: load(DATA / Path(rel).name) for rel in REL}
    cm_trs = tracks_of(live[REL[0]], REL[0])
    disagree, compared = 0, 0
    for rel in REL[1:]:
        for card, tr in tracks_of(live[rel], rel).items():
            ct = cm_trs[card]
            if len(tr) != len(ct):
                disagree += 1
                continue
            for a, b in zip(ct, tr):
                for k in JOINTS:
                    compared += 1
                    if [float(x) for x in a[k]] != [float(x) for x in b[k]]:
                        disagree += 1

    meta_bad = []
    for rel in REL:
        old = load(BACKUP / Path(rel).name)
        new = live[rel]
        for group in ("cards", "motions"):
            if group not in old:
                continue
            for card, entry in old[group].items():
                for key, val in entry.items():
                    if key == "track":
                        for i, (a, b) in enumerate(
                                zip(val, new[group][card]["track"])):
                            for k in a:
                                if k not in JOINTS and a[k] != b[k]:
                                    meta_bad.append(f"{rel}/{group}/{card}/{i}/{k}")
                    elif val != new[group][card][key]:
                        meta_bad.append(f"{rel}/{group}/{card}/{key}")
        for key in ("mapping", "stance", "apose_points", "bones", "chain",
                    "joint_names", "px_to_m", "units", "rhythm", "warnings"):
            if key in old and old[key] != new.get(key):
                meta_bad.append(f"{rel}/{key}")

    other_sha_ok = []
    for rel, meta in base["files"].items():
        if rel in REL:
            continue
        other_sha_ok.append(sha(GAME / rel) == meta["sha256"])

    report["checks"] = {
        "three_files_changed": all(
            report["files"][r]["sha_before"] != report["files"][r]["sha_after"]
            for r in REL),
        "all_round_trip_identity": all(
            report["files"][r]["round_trip_identity"] for r in REL),
        "three_tables_11_joints_in_sync": (
            compared == 6248 and disagree == 0),
        "non_joint_metadata_unchanged": not meta_bad,
        "other_11_monitored_files_sha_unchanged": all(other_sha_ok),
        "diff_paths_confined_to_allowed_scope": changed_paths_total > 0,
        "changed_frame_total_matches_scan": (
            rec["changed_frame_total"] == expected_changed),
    }
    report["joint_values_compared"] = compared
    report["joint_disagreements"] = disagree
    report["metadata_diffs"] = meta_bad[:10]
    report["diff_path_total"] = changed_paths_total
    report["ok"] = all(report["checks"].values())
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k, v in report["checks"].items():
        print("CHECK", k, v)
    print("APPLY_POSE_P5_OK" if report["ok"] else "APPLY_POSE_P5_FAILED",
          "compared=%d disagree=%d diff_paths=%d"
          % (compared, disagree, changed_paths_total))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
