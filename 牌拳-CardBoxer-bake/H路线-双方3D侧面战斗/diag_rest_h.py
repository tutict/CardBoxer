"""量化 A(foe) 与 E(player) 两套 13 骨 rest 的差异，判断能否共用 motion_input。"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
d = json.loads((HERE / "data" / "blend_probe_h.json").read_text(encoding="utf-8"))
f = d["blends"]["foe"]["rigs"][0]["bones"]
p = d["blends"]["player"]["rigs"][0]["bones"]
print("name                 foe_head                       player_head                    dhead     dmatrix_max")
rows = []
for a, b in zip(f, p):
    dh = [round(x - y, 6) for x, y in zip(a["head"], b["head"])]
    dt = [round(x - y, 6) for x, y in zip(a["tail"], b["tail"])]
    dm = [round(abs(x - y), 8) for x, y in zip(a["matrix_local"],
                                              b["matrix_local"])]
    dist = round(sum(x * x for x in dh) ** 0.5, 6)
    rows.append({"bone": a["name"], "dhead": dh, "dtail": dt,
                 "dhead_dist": dist, "dmatrix_max": max(dm)})
    print(f"{a['name']:<20} {str(a['head']):<29} {str(b['head']):<29} "
          f"{dist:<9} {max(dm):<12}")
print("MAX_DHEAD_DIST", max(r["dhead_dist"] for r in rows))
print("MAX_DMATRIX", max(r["dmatrix_max"] for r in rows))
print("BONES_WITH_DIFF", [r["bone"] for r in rows if r["dhead_dist"] > 1e-6])
out = HERE / "data" / "rest_diff_h.json"
out.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
               encoding="utf-8")
