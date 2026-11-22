"""只读核查：diag_stack.py 的 deleted_ratio 是否把塌缩壳判漏了。

打印直方图、missing 顶点总量，以及 tall/head 分界附近的具体壳，
用于决定「被删 vs 保留」的物理分界，而不是凑一个让判据变绿的阈值。
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
rows = json.loads((HERE / "data" / "stack_shells.json")
                  .read_text(encoding="utf-8"))["shells"]
N = len(rows)
print("SHELLS", N)
print("MISSING_VERTS_TOTAL", sum(r["missing_verts_in_b"] for r in rows))
print("VERTS_TOTAL", sum(r["verts"] for r in rows))

buckets = Counter()
for r in rows:
    q = r["deleted_ratio"]
    if q == 0:
        buckets["00_exact_zero"] += 1
    elif q < 0.1:
        buckets["01_0_to_10"] += 1
    elif q < 0.3:
        buckets["02_10_to_30"] += 1
    elif q < 0.5:
        buckets["03_30_to_50"] += 1
    elif q < 0.7:
        buckets["04_50_to_70"] += 1
    elif q < 0.9:
        buckets["05_70_to_90"] += 1
    elif q < 1.0:
        buckets["06_90_to_100"] += 1
    else:
        buckets["07_exact_one"] += 1
for k in sorted(buckets):
    print("BUCKET", k, buckets[k])

print("--- 非零但 <0.9 的壳里，顶点最多的 15 个 ---")
mid = [r for r in rows if 0 < r["deleted_ratio"] < 0.9]
for r in sorted(mid, key=lambda r: -r["verts"])[:15]:
    print(" ", r["shell_id"], "v", r["verts"], "miss",
          r["missing_verts_in_b"], "ratio", r["deleted_ratio"],
          "ctr", r["centroid"], "cyan", r["cyan_faces"])

tall = [r for r in rows
        if (r["hi"][1] - r["lo"][1]) > 0.50
        and (r["hi"][0] - r["lo"][0]) < 0.35]
print("--- TALL STRIPS", len(tall), "---")
for r in tall:
    print(" ", r["shell_id"], "v", r["verts"], "miss",
          r["missing_verts_in_b"], "ratio", r["deleted_ratio"],
          "lo", r["lo"], "hi", r["hi"], "cyan", r["cyan_faces"],
          "uv", r["uv_bbox"])

print("--- 按 ratio>=0.5 分组的青面分配 ---")
for cut in (0.1, 0.3, 0.5, 0.7, 0.9, 1.0):
    d = [r for r in rows if r["deleted_ratio"] >= cut]
    k = [r for r in rows if r["deleted_ratio"] < cut]
    print(f"  cut={cut}: shells del={len(d)} kept={len(k)} "
          f"verts_del={sum(r['verts'] for r in d)} "
          f"cyan_del={sum(r['cyan_faces'] for r in d)} "
          f"cyan_kept={sum(r['cyan_faces'] for r in k)}")
