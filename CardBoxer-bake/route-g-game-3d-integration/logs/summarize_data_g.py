"""只读汇总 G 路线 data/*.json 的判据状态，供验证记录引用。"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
NAMES = [
    "ab_g.json", "static_ab_g.json", "side_view_probe.json",
    "side_stance_probe.json", "side_stance_scan.json",
    "subviewport_probe.json", "three_d_ab.json",
    "baseline_project_g.json", "all_checks_before.json",
    "all_checks_after.json",
]
for name in NAMES:
    d = json.loads((HERE / "data" / name).read_text(encoding="utf-8"))
    print("===", name)
    print("keys:", list(d.keys()))
    print("checks:", d.get("checks"))
    print("ok:", d.get("ok"), "failed:", d.get("failed"))
