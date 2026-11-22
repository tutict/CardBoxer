# -*- coding: utf-8 -*-
"""诊断：把 attack 轨的 f_hand / shoulder 逐帧摆平，核清「伸展」到底是前伸还是后拉。

纯读盘，不改任何文件。产出 data/arm_axes.json + stdout 表。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from pose_cost import CM_PATH, JOINTS, load, tracks_of

HERE = Path(__file__).resolve().parent
CM = load(CM_PATH)
TRS = tracks_of(CM)
ST = CM["stance"]


def d(a, b):
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


out = {"stance": {"shoulder": ST["shoulder"], "f_hand": ST["f_hand"]},
       "tracks": {}}
for card, tr in TRS.items():
    ph = [str(f.get("phase", "react")) for f in tr]
    if "active" not in ph:
        continue
    rows = []
    for i, f in enumerate(tr):
        sh, fh = f["shoulder"], f["f_hand"]
        rows.append({
            "i": i, "phase": ph[i],
            "f_hand": [float(x) for x in fh],
            "shoulder": [float(x) for x in sh],
            "forward_ext_px": round(float(fh[0]) - float(sh[0]), 4),
            "reach_px": round(d(fh, sh), 4),
            "mf_px": round(d(fh, ST["f_hand"]), 4),
        })
    out["tracks"][card] = rows

(HERE / "data" / "arm_axes.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

st_fwd = float(ST["f_hand"][0]) - float(ST["shoulder"][0])
st_reach = d(ST["f_hand"], ST["shoulder"])
print("stance forward_ext=%.3f reach=%.3f" % (st_fwd, st_reach))
for card, rows in out["tracks"].items():
    print("\n=== %s (%d 帧) ===" % (card, len(rows)))
    print("  i  phase     f_hand.x  f_hand.y  sh.x   fwd_ext   reach     mf")
    for r in rows:
        print("%3d  %-8s %9.2f %9.2f %6.1f %9.2f %9.2f %8.2f"
              % (r["i"], r["phase"], r["f_hand"][0], r["f_hand"][1],
                 r["shoulder"][0], r["forward_ext_px"], r["reach_px"],
                 r["mf_px"]))
    mx_fwd = max(rows, key=lambda r: r["forward_ext_px"])
    mx_reach = max(rows, key=lambda r: r["reach_px"])
    print("  MAX fwd_ext  @%d %s = %.3f"
          % (mx_fwd["i"], mx_fwd["phase"], mx_fwd["forward_ext_px"]))
    print("  MAX reach    @%d %s = %.3f"
          % (mx_reach["i"], mx_reach["phase"], mx_reach["reach_px"]))
print("\nWROTE data/arm_axes.json")
