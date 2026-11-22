"""B 路线 P1 看图反馈：定位侧视图里那条没被删掉的细长飘带壳。

b-after-side.png 里有一根从头后斜到脚外的细长薄片（V4b 长发飘带）。
P0 的 CAPE_OR_PANEL 规则要求 y 或 x 跨度够大，几乎垂直的薄片会漏判。
本脚本按「形状」补扫：z 跨度大 + 横向窄 + 顶点少 + 尚未被删。

只读，输出 data/strip_candidates_b.json，列候选壳 ID 供下一轮隔离渲染确认。
用法：python diag_strip_b.py
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ISOLATE = HERE / "data" / "shell_isolate_b.json"
TARGETS = HERE / "data" / "shell_targets_b.json"
OUT = HERE / "data" / "strip_candidates_b.json"

# 订正：第一版把 verts 上限设 1200、z_span 设 0.90，扫出 0 个候选。
# 那条细长片可能是高顶点数的薄壳，或 z 跨度没到 0.9。
# 改为「几乎不设门槛，按 z_span 降序看全部非目标壳」，让数据说话。
Z_SPAN_MIN = 0.50
VERTS_MAX = 64024


def main() -> int:
    iso = json.loads(ISOLATE.read_text(encoding="utf-8"))
    tg = json.loads(TARGETS.read_text(encoding="utf-8"))
    deleted = set(tg["target_shell_ids"])
    # 诊断：先无条件看全表 z_span 分布，避免「过滤条件写错 → 0 个候选」
    # 被误读成「没有细长壳」。
    spans = sorted(
        ((round(r["hi"][2] - r["lo"][2], 4), r["shell_id"],
          r["verts"], r["group"], r["shell_id"] in deleted)
         for r in iso["shells_table"]), reverse=True)
    print("TABLE", len(iso["shells_table"]), "DELETED", len(deleted))
    print("TOP_SPANS", spans[:12])
    rows = []
    for r in iso["shells_table"]:
        if r["shell_id"] in deleted or r["verts"] > VERTS_MAX:
            continue
        zspan = r["hi"][2] - r["lo"][2]
        xspan = r["hi"][0] - r["lo"][0]
        yspan = r["hi"][1] - r["lo"][1]
        if zspan <= Z_SPAN_MIN:
            continue
        rows.append({
            "shell_id": r["shell_id"], "verts": r["verts"],
            "group": r["group"], "region": r["region"],
            "z_span": round(zspan, 4), "x_span": round(xspan, 4),
            "y_span": round(yspan, 4),
            "aspect": round(zspan / max(xspan, yspan, 1e-6), 2),
            "lo": r["lo"], "hi": r["hi"], "centroid": r["centroid"],
            "uv_bbox": r["uv_bbox"], "tex": r["tex"],
        })
    rows.sort(key=lambda d: -d["z_span"])
    by_group = {}
    for d in rows:
        by_group[d["group"]] = by_group.get(d["group"], 0) + 1
    report = {
        "source": str(ISOLATE), "target_spec": str(TARGETS),
        "rule": {"z_span_min": Z_SPAN_MIN, "verts_max": VERTS_MAX,
                 "exclude": "已在 shell_targets_b.json 的 195 个目标壳"},
        "candidates": rows, "count": len(rows),
        "by_group": by_group,
        "top10_ids": [d["shell_id"] for d in rows[:10]],
        "ok": len(rows) > 0,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("CANDIDATES", len(rows), "BY_GROUP", by_group)
    for d in rows[:20]:
        print("SHELL", d["shell_id"], "verts", d["verts"],
              "zspan", d["z_span"], "x/y", d["x_span"], d["y_span"],
              "aspect", d["aspect"], "z", d["lo"][2], d["hi"][2],
              "group", d["group"])
    print("STRIP_SCAN_B_OK" if report["ok"]
          else "STRIP_SCAN_B_EMPTY")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
