"""临时工具：dump 本区大 JSON 的顶层键，供写判据时对齐字段名。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = HERE / "data"
for name in sys.argv[1:]:
    p = D / name
    obj = json.loads(p.read_text(encoding="utf-8"))
    print("===", name, "===")
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, dict):
                print(f"  {k}: dict keys={list(v)[:12]}")
            elif isinstance(v, list):
                print(f"  {k}: list len={len(v)} first_type="
                      f"{type(v[0]).__name__ if v else '-'}")
            else:
                print(f"  {k}: {type(v).__name__} = {str(v)[:90]}")
    else:
        print("  ROOT", type(obj).__name__, len(obj))
