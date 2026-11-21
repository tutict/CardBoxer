# -*- coding: utf-8 -*-
"""P5 读盘侦察：纯读盘 + 纯计算，不改任何文件。

产出 data/tables_probe.json 与 stdout 摘要。
目的：在写「招牌动作规格」之前，先把 15 轨动作表的真实形状、
坐标系、相位分布、三表同步关系量清楚，避免凭印象定规格。
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "牌拳-CardBoxer"
DATA = GAME / "data"

JOINTS = [
    "hip", "shoulder", "head", "f_elbow", "f_hand",
    "b_elbow", "b_hand", "f_knee", "f_foot", "b_knee", "b_foot",
]

TABLES = {
    "card_motion": DATA / "card_motion.json",
    "motion_input": DATA / "motion_input.json",
    "motion_input_foe": DATA / "motion_input_foe.json",
}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load(p: Path) -> dict:
    return json.loads(p.read_bytes().decode("utf-8-sig"))


def track_of(node) -> list:
    """兼容几种容器形态；frames 可能是 int，不能当 list 用。"""
    if isinstance(node, list):
        return node
    if isinstance(node, dict):
        for key in ("track", "poses", "keys", "keyframes"):
            value = node.get(key)
            if isinstance(value, list):
                return value
    return []


def joints_of(frame: dict) -> dict:
    return {k: tuple(float(x) for x in frame[k]) for k in JOINTS}


def dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def bbox(joints: dict) -> tuple:
    xs = [p[0] for p in joints.values()]
    ys = [p[1] for p in joints.values()]
    return (min(xs), min(ys), max(xs), max(ys))


def main() -> None:
    raw = {name: load(path) for name, path in TABLES.items()}
    out: dict = {
        "files": {
            name: {"path": str(path), "bytes": path.stat().st_size,
                   "sha256": sha(path)}
            for name, path in TABLES.items()
        },
        "root_keys": {name: sorted(obj.keys()) for name, obj in raw.items()},
        "tracks": {},
        "sync": {},
        "geometry": {},
    }

    cm = raw["card_motion"]
    print("== card_motion.json ==")
    print("root keys:", sorted(cm.keys()))
    print("units:", cm.get("units"))
    print("rhythm:", cm.get("rhythm"))
    print("stance:", json.dumps(cm.get("stance"), ensure_ascii=False)[:600])
    for group in ("cards", "motions"):
        node = cm.get(group, {})
        print(f"{group}: {len(node)} tracks -> {sorted(node.keys())}")
        for card, val in node.items():
            tr = track_of(val)
            if not tr:
                print(f"  {card}: NO TRACK, keys={list(val.keys()) if isinstance(val, dict) else type(val)}")
                continue
            phases = [str(f.get("phase", "?")) for f in tr]
            seq = []
            for ph in phases:
                if not seq or seq[-1][0] != ph:
                    seq.append([ph, 1])
                else:
                    seq[-1][1] += 1
            out["tracks"][f"{group}/{card}"] = {
                "group": group, "card": card, "frames": len(tr),
                "frame_keys": sorted(tr[0].keys()),
                "phase_runs": seq,
                "declared": {k: v for k, v in val.items()
                             if not isinstance(v, (list, dict))}
                if isinstance(val, dict) else {},
            }
            print(f"  {card:10s} n={len(tr):3d} phases={seq}")

    mi = raw["motion_input"]
    mf = raw["motion_input_foe"]
    print("== motion_input*.json ==")
    print("player root keys:", sorted(mi.keys()))
    print("foe    root keys:", sorted(mf.keys()))
    print("player mapping:", json.dumps(mi.get("mapping"), ensure_ascii=False))
    print("player cards:", len(mi.get("cards", {})))
    print("foe    cards:", len(mf.get("cards", {})))
    out["mapping"] = mi.get("mapping")
    out["apose_equal"] = mi.get("apose_points") == mf.get("apose_points")
    out["stance_equal"] = mi.get("stance") == mf.get("stance")

    # 三表 11 关节逐值一致性（P4 后应保持同步）
    cm_tracks = {}
    for group in ("cards", "motions"):
        for card, val in cm.get(group, {}).items():
            cm_tracks[card] = track_of(val)
    disagree = []
    checked = 0
    for side, obj in (("player", mi), ("foe", mf)):
        for card, val in obj.get("cards", {}).items():
            tr = track_of(val)
            ct = cm_tracks.get(card)
            if ct is None or len(ct) != len(tr):
                disagree.append(f"{side}/{card}/len:{len(tr)}vs{len(ct) if ct else None}")
                continue
            for i, (a, b) in enumerate(zip(ct, tr)):
                ja, jb = joints_of(a), joints_of(b)
                for k in JOINTS:
                    checked += 1
                    if ja[k] != jb[k]:
                        disagree.append(f"{side}/{card}/{i}/{k}")
    out["sync"] = {
        "joint_values_checked": checked,
        "disagreements": disagree[:20],
        "disagreement_count": len(disagree),
        "cm_vs_mi_identical": len(disagree) == 0,
    }
    print("== 三表 11 关节同步 ==")
    print(f"checked={checked} disagreements={len(disagree)}")

    # 几何基线：用 card_motion 的 stance
    st = cm.get("stance")
    st_j = None
    if isinstance(st, dict):
        if all(k in st for k in JOINTS):
            st_j = joints_of(st)
        else:
            print("stance keys:", sorted(st.keys()))
    if st_j is None:
        # 退路：用第一轨首帧；写进报告，不假装是 stance
        first = next(iter(cm_tracks.values()))[0]
        st_j = joints_of(first)
        out["stance_source"] = "fallback:first_frame_of_first_track"
    else:
        out["stance_source"] = "card_motion.stance"
    out["stance_joints"] = {k: list(v) for k, v in st_j.items()}
    print("== stance ==")
    print(json.dumps(out["stance_joints"], ensure_ascii=False))
    print("stance bbox:", bbox(st_j))

    # 每轨几何：前手伸展、重心高度、剪影面积、整帧定格段
    for key, info in out["tracks"].items():
        group, card = key.split("/", 1)
        tr = cm_tracks[card]
        reach = [dist(joints_of(f)["f_hand"], joints_of(f)["shoulder"]) for f in tr]
        hip_y = [joints_of(f)["hip"][1] for f in tr]
        areas = []
        for f in tr:
            x0, y0, x1, y1 = bbox(joints_of(f))
            areas.append((x1 - x0) * (y1 - y0))
        dup = 0
        for a, b in zip(tr, tr[1:]):
            if joints_of(a) == joints_of(b):
                dup += 1
        g = {
            "reach_stance": round(dist(st_j["f_hand"], st_j["shoulder"]), 4),
            "reach_min": round(min(reach), 4),
            "reach_max": round(max(reach), 4),
            "reach_gain_px": round(max(reach) - dist(st_j["f_hand"], st_j["shoulder"]), 4),
            "reach_argmax": reach.index(max(reach)),
            "hip_y_stance": round(st_j["hip"][1], 4),
            "hip_y_min": round(min(hip_y), 4),
            "hip_y_max": round(max(hip_y), 4),
            "hip_drop_max_px": round(max(hip_y) - st_j["hip"][1], 4),
            "bbox_area_stance": round((bbox(st_j)[2] - bbox(st_j)[0]) * (bbox(st_j)[3] - bbox(st_j)[1]), 4),
            "bbox_area_max": round(max(areas), 4),
            "exact_hold_pairs": dup,
        }
        out["geometry"][key] = g

    print("== 每轨几何（reach_gain / hip_drop / hold） ==")
    for key, g in out["geometry"].items():
        print(f"{key:24s} n={out['tracks'][key]['frames']:3d} "
              f"reach+{g['reach_gain_px']:8.3f}@{g['reach_argmax']:3d} "
              f"drop+{g['hip_drop_max_px']:7.3f} "
              f"area {g['bbox_area_stance']:9.1f}->{g['bbox_area_max']:9.1f} "
              f"hold={g['exact_hold_pairs']:3d}")

    dst = HERE / "data" / "tables_probe.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("WROTE", dst)


if __name__ == "__main__":
    main()
