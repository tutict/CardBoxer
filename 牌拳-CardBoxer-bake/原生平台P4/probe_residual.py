"""临时诊断：为什么 MICRO 后仍有精确平台残留（不改任何文件）。"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from evaluate_candidates import (  # noqa: E402
    CAP, DIRECTIONS, EXACT_EPS, GAME, LEG_BONES, Ctx, build_micro,
    frame_joints, leg_value, segments_of,
)

mi = json.loads((GAME / "data" / "motion_input.json").read_text(
    encoding="utf-8"))
cm = json.loads((GAME / "data" / "card_motion.json").read_text(
    encoding="utf-8"))
ctx = Ctx(mi)
tracks = {k: v["track"] for k, v in cm["cards"].items()}
tracks.update({k: v["track"] for k, v in cm["motions"].items()})

A = 0.3
residual = []
all_pairs = 0
for card, track in tracks.items():
    base = [frame_joints(f, ctx.keys) for f in track]
    raw0 = [ctx.raw(j) for j in base]
    flags = [any(abs(raw0[i + 1][b] - raw0[i][b]) < EXACT_EPS
                 for b in LEG_BONES) for i in range(len(track) - 1)]
    mod = build_micro(base, flags, A)
    raw1 = [ctx.raw(j) for j in mod]
    out1 = [{b: leg_value(v) for b, v in r.items()} for r in raw1]
    in_seg = set()
    for s, m in segments_of(flags):
        in_seg.update(range(s, s + m + 2))
    for i in range(len(track) - 1):
        for b in LEG_BONES:
            all_pairs += 1
            if abs(out1[i + 1][b] - out1[i][b]) >= EXACT_EPS:
                continue
            moved = math.dist(base[i + 1]["f_knee"],
                              mod[i + 1]["f_knee"])
            residual.append({
                "card": card, "frame": i, "bone": b,
                "raw0_a": round(raw0[i][b], 6),
                "raw1_a": round(raw1[i][b], 6),
                "raw1_b": round(raw1[i + 1][b], 6),
                "raw_delta": round(raw1[i + 1][b] - raw1[i][b], 8),
                "out1_a": round(out1[i][b], 9),
                "out1_b": round(out1[i + 1][b], 9),
                "i_in_segment": i in in_seg,
                "f_knee_moved_px": round(moved, 6),
                "flag": flags[i],
            })

print("ALL_PAIRS", all_pairs, "RESIDUAL", len(residual))
print("BY_CARD", dict(sorted(Counter(r["card"] for r in residual).items())))
print("BY_BONE", dict(sorted(Counter(r["bone"] for r in residual).items())))
print("IN_SEGMENT", sum(r["i_in_segment"] for r in residual))
print("FLAG_TRUE", sum(r["flag"] for r in residual))
print("F_KNEE_MOVED_ZERO", sum(r["f_knee_moved_px"] == 0
                              for r in residual))
print("RAW_DELTA_ZERO", sum(abs(r["raw_delta"]) < 1e-9
                            for r in residual))
print("--- first 20 ---")
for r in residual[:20]:
    print(r)
