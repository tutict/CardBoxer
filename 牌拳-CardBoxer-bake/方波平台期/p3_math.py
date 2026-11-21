"""P3 共用公式层：与 rig_driver.gd::retarget_delta 逐字同口径。

运行时驱动现在按 mapping.leg_mode 分派：
  hard —— clampf(raw, -cap, cap)（P2 上线态）
  atan —— cap*(2/PI)*atan((PI/2)*raw/cap)（P3 落地态）
本模块把「先拿 raw，再按 mode 映射」独立实现一遍，供探针 runner、
板子、承重判据复用；绝不复用被测脚本的结论。

CLI：python p3_math.py  打印 hard9 下被 clamp 削平的最长连续帧段。
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


@lru_cache(maxsize=1)
def inputs():
    mi = json.loads((GAME / "data" / "motion_input.json").read_text(
        encoding="utf-8"))
    cm = json.loads((GAME / "data" / "card_motion.json").read_text(
        encoding="utf-8"))
    tracks = {k: v["track"] for k, v in cm["cards"].items()}
    tracks.update({k: v["track"] for k, v in cm["motions"].items()})
    mapping = dict(mi["mapping"])
    mapping["leg_cap_deg"] = 1e9  # 拿未经 clamp 的原始腿角
    stance_j = {k: tuple(v) for k, v in mi["stance"].items()}
    return {"mi": mi, "cm": cm, "tracks": tracks,
            "mapping": mapping, "stance_j": stance_j,
            "stance_points": make_points(stance_j),
            "keys": list(mi["joint_names"]), "chain": mi["chain"]}


def legs_raw(card: str, frame: int) -> dict:
    d = inputs()
    if card == "stance":
        fj = d["stance_j"]
    else:
        body = d["tracks"].get(card)
        if body is None or frame < 0 or frame >= len(body):
            return {}
        fj = {k: tuple(body[frame][k]) for k in d["keys"]}
    _delta, raw = retarget_delta(fj, d["stance_j"], d["chain"],
                                 d["mapping"], d["stance_points"])
    return {b: float(raw[b]) for b in LEG_BONES}


def leg_value(x: float, cap: float, mode: str) -> float:
    if mode == "atan":
        return cap * (2.0 / math.pi) * math.atan(
            (math.pi / 2.0) * x / cap)
    if mode == "tanh":
        return cap * math.tanh(x / cap)
    return max(-cap, min(cap, x))


def expected_delta(card: str, frame: int, mode: str,
                   cap: float) -> dict:
    """13 骨 delta（度），腿骨按指定 mode/cap 映射。"""
    d = inputs()
    if card == "stance":
        fj = d["stance_j"]
    else:
        body = d["tracks"].get(card)
        if body is None or frame < 0 or frame >= len(body):
            return {}
        fj = {k: tuple(body[frame][k]) for k in d["keys"]}
    delta, raw = retarget_delta(fj, d["stance_j"], d["chain"],
                                d["mapping"], d["stance_points"])
    out = {k: float(v) for k, v in delta.items()}
    for b in LEG_BONES:
        out[b] = leg_value(float(raw[b]), cap, mode)
    return out


def longest_clamp_runs(cap: float = 9.0, top: int = 10) -> list[dict]:
    """找出 hard cap 下「raw 不同但输出相同」的最长连续帧段。"""
    out = []
    for card, track in inputs()["tracks"].items():
        for bone in LEG_BONES:
            vals = [max(-cap, min(cap, legs_raw(card, i)[bone]))
                    for i in range(len(track))]
            raws = [legs_raw(card, i)[bone] for i in range(len(track))]
            run_start, run_len = 0, 0
            for i in range(1, len(vals)):
                flat = abs(vals[i] - vals[i - 1]) < 1e-6
                raw_diff = abs(raws[i] - raws[i - 1]) >= 1e-6
                if flat and raw_diff:
                    if run_len == 0:
                        run_start = i - 1
                    run_len += 1
                else:
                    if run_len:
                        out.append({"card": card, "bone": bone,
                                    "start": run_start,
                                    "end": i - 1,
                                    "pairs": run_len,
                                    "out_deg": round(vals[i - 1], 3),
                                    "raw_span_deg": [
                                        round(min(raws[run_start:i]), 2),
                                        round(max(raws[run_start:i]), 2)]})
                    run_len = 0
            if run_len:
                out.append({"card": card, "bone": bone,
                            "start": run_start, "end": len(vals) - 1,
                            "pairs": run_len,
                            "out_deg": round(vals[-1], 3),
                            "raw_span_deg": [
                                round(min(raws[run_start:]), 2),
                                round(max(raws[run_start:]), 2)]})
    return sorted(out, key=lambda r: (-r["pairs"], r["card"], r["bone"]))[
        :top]


if __name__ == "__main__":
    for r in longest_clamp_runs():
        print("CLAMP_RUN", r)
