"""P4 共用公式层：与 rig_driver.gd::retarget_delta 同口径，但按「哪张表」分派。

与 p3_math.py 的差别：P4 的 A/B 是**换动作表**，不是换 mapping。
  shipped / reapplied —— 读 GAME/data/card_motion.json（micro2 上线表）
  rolled_back         —— 读 orig/pre-p4/card_motion.json（P3 上线态原表）
mapping 两版完全相同（atan / 12.0），stance / chain / apose_points 也相同。

供 run_p4_probe.py、make_p4_boards.py、verify_native.py 复用；
绝不复用被测脚本的结论。
"""
from __future__ import annotations

import json
import math
import sys
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "牌拳-CardBoxer"
DIAG = BAKE / "动作优化诊断"
sys.path.insert(0, str(DIAG))
from diag_motion import make_points, retarget_delta  # noqa: E402

LEG_BONES = ("thigh_f", "shin_f", "thigh_b", "shin_b")
SHIPPED_CM = GAME / "data" / "card_motion.json"
LEGACY_CM = HERE / "orig" / "pre-p4" / "card_motion.json"


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def tracks_of(cm: dict) -> dict:
    out = {k: v["track"] for k, v in cm["cards"].items()}
    out.update({k: v["track"] for k, v in cm["motions"].items()})
    return out


@lru_cache(maxsize=1)
def inputs():
    mi = load(GAME / "data" / "motion_input.json")
    stance_j = {k: tuple(v) for k, v in mi["stance"].items()}
    mapping = dict(mi["mapping"])
    mapping["leg_cap_deg"] = 1e9  # 先拿未经软限幅的原始腿角
    return {"mapping": mapping, "stance_j": stance_j,
            "stance_points": make_points(stance_j),
            "keys": list(mi["joint_names"]), "chain": mi["chain"],
            "cap": float(mi["mapping"]["leg_cap_deg"]),
            "mode": str(mi["mapping"].get("leg_mode", "hard"))}


@lru_cache(maxsize=2)
def tracks(which: str) -> dict:
    if which not in ("shipped", "rolled_back"):
        raise ValueError(which)
    return tracks_of(load(LEGACY_CM if which == "rolled_back"
                          else SHIPPED_CM))


def leg_value(x: float, cap: float, mode: str) -> float:
    if mode == "atan":
        return cap * (2.0 / math.pi) * math.atan(
            (math.pi / 2.0) * x / cap)
    if mode == "tanh":
        return cap * math.tanh(x / cap)
    return max(-cap, min(cap, x))


def expected_delta(card: str, frame: int, which: str = "shipped") -> dict:
    """13 骨 delta（度）；which 决定从哪张动作表取 11 关节。"""
    d = inputs()
    if card == "stance":
        fj = d["stance_j"]
    else:
        body = tracks(which).get(card)
        if body is None or frame < 0 or frame >= len(body):
            return {}
        fj = {k: tuple(body[frame][k]) for k in d["keys"]}
    delta, raw = retarget_delta(fj, d["stance_j"], d["chain"],
                                d["mapping"], d["stance_points"])
    out = {k: float(v) for k, v in delta.items()}
    for b in LEG_BONES:
        out[b] = leg_value(float(raw[b]), d["cap"], d["mode"])
    return out


def leg_peak(card: str, frame: int, which: str = "shipped") -> float:
    d = expected_delta(card, frame, which)
    return max((abs(d[b]) for b in LEG_BONES), default=0.0)
