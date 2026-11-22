# -*- coding: utf-8 -*-
"""P5 姿态语言指标层：把「招牌动作语言」翻译成 11 关节表上可复算的数。

坐标系来自 card_motion.json:units —— game px / 原点脚下 / +x 向前 / -y 向上。
所以 hip.y 变大 = 质心下沉；f_hand.x 变小 = 击打手后收。

本模块纯函数、只读盘，不写任何文件；被 verify_pose_spec.py、
diag_pose_gap.py、evaluate_pose_candidates.py 共用，保证三处口径一致。
"""
from __future__ import annotations

import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parent.parent / "CardBoxer"

JOINTS = [
    "hip", "shoulder", "head", "f_elbow", "f_hand",
    "b_elbow", "b_hand", "f_knee", "f_foot", "b_knee", "b_foot",
]

METRIC_NAMES = [
    "windup_recoil_px", "windup_hip_drop_px",
    "peak_reach_gain_px", "peak_reach_argmax", "peak_reach_phase",
    "peak_bbox_gain_pct", "impact_hold_len",
    "recover_overshoot_px", "end_drift_px",
    "foot_ground_max_px", "stance_width_max_px",
    "arc_deviation_px", "exact_hold_pairs",
]


def load_json(path: Path) -> dict:
    import json
    return json.loads(path.read_bytes().decode("utf-8-sig"))


def tracks_of(cm: dict) -> dict:
    """card_motion.json 的 12 卡 + 3 受击，统一成 {name: (group, track)}。"""
    out = {}
    for group in ("cards", "motions"):
        for name, node in cm.get(group, {}).items():
            tr = node if isinstance(node, list) else node.get("track")
            if isinstance(tr, list) and tr:
                out[name] = (group, tr)
    return out


def joints_of(frame: dict) -> dict:
    return {k: tuple(float(x) for x in frame[k]) for k in JOINTS}


def dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def reach(j: dict, side: str = "f") -> float:
    return dist(j[f"{side}_hand"], j["shoulder"])


def bbox_area(j: dict) -> float:
    xs = [p[0] for p in j.values()]
    ys = [p[1] for p in j.values()]
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def phases_of(track: list) -> list[str]:
    """react 轨没有 phase 字段，统一标 react（不假装它有三段式）。"""
    return [str(f.get("phase", "react")) for f in track]


def point_line_distance(p, a, b) -> float:
    """点 p 到线段 ab 所在直线的垂距；ab 退化时退化为两点距离。"""
    dx, dy = b[0] - a[0], b[1] - a[1]
    den = math.hypot(dx, dy)
    if den < 1e-12:
        return dist(p, a)
    return abs(dx * (a[1] - p[1]) - (a[0] - p[0]) * dy) / den


def metrics(track: list, stance: dict, name: str = "") -> dict:
    """单轨全量指标。所有返回值必须是可 JSON 序列化的有限数或字符串。"""
    js = [joints_of(f) for f in track]
    ph = phases_of(track)
    n = len(js)
    st_reach = reach(stance)
    st_area = bbox_area(stance)

    reaches = [reach(j) for j in js]
    gains = [r - st_reach for r in reaches]
    peak_i = max(range(n), key=lambda i: gains[i])
    areas = [bbox_area(j) for j in js]

    wind = [i for i, p in enumerate(ph) if p == "windup"]
    # 没有 windup 段（react 轨）时用前 1/3，不伪造语义；报告里会标 scope。
    if not wind:
        wind = list(range(max(1, n // 3)))

    recoil = max(0.0, stance["f_hand"][0] - min(js[i]["f_hand"][0] for i in wind))
    hip_drop = max(js[i]["hip"][1] for i in wind) - stance["hip"][1]

    # 命中定格：峰值帧之后连续「整帧 11 关节完全相同」的帧数。
    hold = 0
    for i in range(peak_i + 1, n):
        if js[i] == js[i - 1]:
            hold += 1
        else:
            break

    # 随动过冲：峰值帧之后 f_hand.x 是否还继续向前越过峰值帧。
    overshoot = max(0.0, max(js[i]["f_hand"][0] for i in range(peak_i, n))
                    - js[peak_i]["f_hand"][0])
    end_drift = max(dist(js[-1][k], stance[k]) for k in JOINTS)
    foot_ground = max(max(abs(j["f_foot"][1]), abs(j["b_foot"][1])) for j in js)
    width = max(abs(j["f_foot"][0] - j["b_foot"][0]) for j in js)

    # 弧线：起手首帧 -> reach 峰值帧之间，f_hand 轨迹偏离两端连线的最大垂距。
    a, b = js[0]["f_hand"], js[peak_i]["f_hand"]
    arc = max(point_line_distance(js[i]["f_hand"], a, b)
              for i in range(0, peak_i + 1))

    exact_hold = sum(1 for i in range(1, n) if js[i] == js[i - 1])

    return {
        "windup_recoil_px": round(recoil, 4),
        "windup_hip_drop_px": round(hip_drop, 4),
        "peak_reach_gain_px": round(gains[peak_i], 4),
        "peak_reach_argmax": peak_i,
        "peak_reach_phase": ph[peak_i],
        "peak_bbox_gain_pct": round(100.0 * (max(areas) / st_area - 1.0), 4),
        "impact_hold_len": hold,
        "recover_overshoot_px": round(overshoot, 4),
        "end_drift_px": round(end_drift, 4),
        "foot_ground_max_px": round(foot_ground, 4),
        "stance_width_max_px": round(width, 4),
        "arc_deviation_px": round(arc, 4),
        "exact_hold_pairs": exact_hold,
    }


def all_metrics(cm: dict) -> dict:
    """全 15 轨；返回值供规格判据、差距诊断、候选评估共用。"""
    stance = joints_of(cm["stance"])
    return {name: metrics(tr, stance, name)
            for name, (_group, tr) in tracks_of(cm).items()}


def peak_pose_distance(cm: dict, a: str, b: str) -> float:
    """两条轨各自 reach 峰值帧的 11 关节逐点距离之和，用于 L8 可辨性。"""
    stance = joints_of(cm["stance"])
    trs = tracks_of(cm)
    out = []
    for name in (a, b):
        js = [joints_of(f) for f in trs[name][1]]
        i = max(range(len(js)), key=lambda k: reach(js[k]))
        out.append(js[i])
    return round(sum(dist(out[0][k], out[1][k]) for k in JOINTS), 4)
