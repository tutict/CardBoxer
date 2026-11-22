"""P1 数据层：把 card_motion.json 的 9 卡 + 3 受击轨道扩进两份 motion_input。

纪律：
  - 既有 3 卡（jab/cross/wave）的字典**原样保留**，不重新生成；
  - 两份 motion_input 除 cards 外所有字段原样保留（含 foe 专属 apose_points）；
  - 新轨道每帧只取 11 关节，与既有 track 同形同单位；
  - 不放大任何 mapping 增益（scan_amplitude.py 已证明无需限幅）。

用法：python build_motion_p1.py
产出：游戏 data/motion_input.json、data/motion_input_foe.json
      data/build_motion_p1.json（判据与逐项对账）
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parent.parent / "CardBoxer"
ORIG = HERE / "orig" / "pre-p1"
OUT = HERE / "data" / "build_motion_p1.json"

TARGETS = {
    "motion_input.json": GAME / "data" / "motion_input.json",
    "motion_input_foe.json": GAME / "data" / "motion_input_foe.json",
}
EXISTING = ("jab", "cross", "wave")


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"


def main() -> int:
    cm = json.loads((GAME / "data" / "card_motion.json").read_text(
        encoding="utf-8"))
    src_tracks = {}
    for k, v in cm["cards"].items():
        src_tracks[k] = v["track"]
    for k, v in cm["motions"].items():
        src_tracks[k] = v["track"]

    reports = {}
    for fname, path in TARGETS.items():
        before = json.loads((ORIG / fname).read_text(encoding="utf-8"))
        keys = list(before["joint_names"])
        after = copy.deepcopy(before)
        added = {}
        for name, track in src_tracks.items():
            if name in EXISTING:
                continue
            frames = []
            for f in track:
                frames.append({k: list(f[k]) for k in keys})
            added[name] = {"frames": len(frames), "track": frames}
            after["cards"][name] = added[name]
        text = dump(after)
        path.write_bytes(text.encode("utf-8"))
        readback = json.loads(path.read_text(encoding="utf-8"))

        # 逐项对账，不看上游 ok 字段
        existing_equal = all(
            readback["cards"][k] == before["cards"][k] for k in EXISTING)
        other_equal = all(
            readback[k] == before[k] for k in before if k != "cards")
        added_equal = all(
            readback["cards"][k] == v for k, v in added.items())
        source_equal = all(
            all(readback["cards"][name]["track"][i][k]
                == list(track[i][k]) for k in keys)
            for name, track in src_tracks.items() if name not in EXISTING
            for i in range(len(track)))
        frame_counts_equal = all(
            readback["cards"][name]["frames"] == len(track)
            for name, track in src_tracks.items())
        joint_keys_ok = all(
            set(readback["cards"][name]["track"][i].keys()) == set(keys)
            for name in readback["cards"]
            for i in range(len(readback["cards"][name]["track"])))
        checks = {
            "existing_three_unchanged": existing_equal,
            "non_cards_fields_unchanged": other_equal,
            "added_twelve_tracks": len(added) == 12,
            "cards_total_fifteen": len(readback["cards"]) == 15,
            "added_matches_source_px": added_equal and source_equal,
            "frame_counts_match_source": frame_counts_equal,
            "all_frames_have_11_joints": joint_keys_ok,
            "readback_is_valid_json": readback == after,
        }
        reports[fname] = {
            "path": str(path), "bytes": path.stat().st_size,
            "cards": {k: len(v["track"])
                      for k, v in readback["cards"].items()},
            "added": sorted(added),
            "checks": checks, "ok": all(checks.values()),
        }

    # 两份数据的 cards 必须完全一致；apose_points 允许不同（对手骨架尺寸）
    p = json.loads(TARGETS["motion_input.json"].read_text(encoding="utf-8"))
    f = json.loads(TARGETS["motion_input_foe.json"].read_text(encoding="utf-8"))
    cross = {
        "two_cards_identical": p["cards"] == f["cards"],
        "two_stance_identical": p["stance"] == f["stance"],
        "two_mapping_identical": p["mapping"] == f["mapping"],
        "two_apose_may_differ": p["apose_points"] != f["apose_points"],
    }
    report = {"targets": reports, "cross_file": cross,
              "source": "card_motion.json",
              "ok": all(r["ok"] for r in reports.values())
              and all(cross.values())}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for name, r in reports.items():
        print("FILE", name, r["bytes"], "cards", len(r["cards"]),
              "added", len(r["added"]))
        for k, v in r["checks"].items():
            print("CHECK", name, k, v)
    for k, v in cross.items():
        print("CROSS", k, v)
    print("BUILD_MOTION_P1_OK" if report["ok"]
          else "BUILD_MOTION_P1_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
