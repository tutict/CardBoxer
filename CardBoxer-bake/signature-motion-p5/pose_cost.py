# -*- coding: utf-8 -*-
"""P5 双侧成本公式层：把任意候选 11 关节表换算成 13 骨 delta。

与 rig_driver.gd::retarget_delta 同口径（直接复用 motion-diagnostics/diag_motion.py），
腿骨按 P4 上线的 atan/12.0 软限幅；不新写 retarget 公式，避免两处分叉。
供 design_pose_candidates.py / make_pose_plan.py / #217 的 A/B 复算共用。
"""
from __future__ import annotations

import json
import math
import sys
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "CardBoxer"
DIAG = BAKE / "motion-diagnostics"
sys.path.insert(0, str(DIAG))
from diag_motion import make_points, retarget_delta  # noqa: E402

LEG_BONES = ("thigh_f", "shin_f", "thigh_b", "shin_b")
JOINTS = [
    "hip", "shoulder", "head", "f_elbow", "f_hand",
    "b_elbow", "b_hand", "f_knee", "f_foot", "b_knee", "b_foot",
]
MI_PATH = GAME / "data" / "motion_input.json"
CM_PATH = GAME / "data" / "card_motion.json"


def load(path: Path) -> dict:
    return json.loads(path.read_bytes().decode("utf-8-sig"))


def tracks_of(cm: dict) -> dict:
    out = {k: v["track"] for k, v in cm["cards"].items()}
    out.update({k: v["track"] for k, v in cm["motions"].items()})
    return out


def joints_of(frame: dict, keys=JOINTS) -> dict:
    return {k: tuple(float(x) for x in frame[k]) for k in keys}


@lru_cache(maxsize=1)
def inputs() -> dict:
    mi = load(MI_PATH)
    stance_j = joints_of(mi["stance"])
    cfg = dict(mi["mapping"])
    cfg["leg_cap_deg"] = 1e9  # 先拿原始腿角，再单独软限幅
    return {
        "mapping": cfg,
        "stance_j": stance_j,
        "stance_points": make_points(stance_j),
        "chain": mi["chain"],
        "apose_points": mi["apose_points"],
        "bones": mi["bones"],
        "px_to_m": float(mi["px_to_m"]),
        "cap": float(mi["mapping"]["leg_cap_deg"]),
        "mode": str(mi["mapping"].get("leg_mode", "hard")),
        "arm_gain_deg": dict(mi["mapping"]["arm_gain_deg"]),
    }


def leg_value(x: float, cap: float, mode: str) -> float:
    if mode == "atan":
        return cap * (2.0 / math.pi) * math.atan((math.pi / 2.0) * x / cap)
    if mode == "tanh":
        return cap * math.tanh(x / cap)
    return max(-cap, min(cap, x))


def delta_and_root(frame_j: dict) -> tuple[dict, list]:
    """一帧的 13 骨 delta（度）与 root 位移（米）。"""
    d = inputs()
    delta, raw = retarget_delta(frame_j, d["stance_j"], d["chain"],
                                d["mapping"], d["stance_points"])
    out = {k: float(v) for k, v in delta.items()}
    for b in LEG_BONES:
        out[b] = leg_value(float(raw[b]), d["cap"], d["mode"])
    dx = (frame_j["hip"][0] - d["stance_j"]["hip"][0]) * d["px_to_m"]
    dz = -(frame_j["hip"][1] - d["stance_j"]["hip"][1]) * d["px_to_m"]
    return out, [dx, dz]


def all_deltas(tracks: dict) -> dict:
    """全量 {card: [ {bone: deg}, ... ]}。"""
    return {
        card: [delta_and_root(joints_of(f))[0] for f in track]
        for card, track in tracks.items()
    }


def chebyshev_gap(a: dict, b: dict) -> float:
    """pose_probe.gd::_gap 口径：11 关节逐坐标绝对差的最大值。"""
    w = 0.0
    for k in JOINTS:
        x, y = a[k], b[k]
        w = max(w, abs(float(x[0]) - float(y[0])),
                abs(float(x[1]) - float(y[1])))
    return w


def endpoint_drift(cm: dict, stance_raw: dict) -> tuple[float, str]:
    """pose_probe.gd 的「表内起收招最大漂移」，逐轨首帧/末帧对 stance。"""
    worst, who = 0.0, "none"
    for card, track in tracks_of(cm).items():
        for label, idx in (("frame0", 0), ("last", len(track) - 1)):
            g = chebyshev_gap(track[idx], stance_raw)
            if g > worst:
                worst, who = g, f"{card} {label}"
    return round(worst, 4), who
