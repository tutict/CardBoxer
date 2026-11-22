"""诊断：逐骨打印「相对站架」的旋转增量，定位 puppet 整个人翻转的来源。"""
from __future__ import annotations

import json
import math
from pathlib import Path

from make_puppet import (CHAIN, HERE, JOINTS, TABLE, angle, joints_of,
                         make_points, wrap_pi)

spec = json.loads((HERE / "apose_joints.json").read_text(encoding="utf-8"))
table = json.loads(TABLE.read_text(encoding="utf-8"))
stance = joints_of(table, None, 0)
sp = make_points(stance, 1.0)

for card, frame in [(None, 0), ("jab", 7), ("cross", 11), ("wave", 18), ("wave", 30)]:
    j = joints_of(table, card, frame)
    fp = make_points(j, 1.0)
    print(f"\n=== {card} frame {frame} hip={j['hip']} ===")
    for name, _p, u, v in CHAIN:
        d = math.degrees(wrap_pi(angle(fp[u], fp[v]) - angle(sp[u], sp[v])))
        print(f"  {name:<12} {d:>8.2f} deg   S={sp[u]}->{sp[v]}  F={fp[u]}->{fp[v]}")
