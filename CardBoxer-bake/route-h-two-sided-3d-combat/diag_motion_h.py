"""读 motion_input.json 的 chain / apose_points / mapping 口径。"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
p = BAKE / "route-f-godot-driver" / "data" / "motion_input.json"
d = json.loads(p.read_text(encoding="utf-8"))
print("KEYS", list(d.keys()))
print("bones", d.get("bones"))
print("chain:")
for e in d.get("chain", []):
    print("   ", e)
print("apose_points:")
for k, v in d.get("apose_points", {}).items():
    print("   ", k, v)
print("stance:")
for k, v in d.get("stance", {}).items():
    print("   ", k, v)
print("mapping keys", list(d.get("mapping", {}).keys()))
print("px_to_m", d.get("px_to_m"))
print("cards", {k: v.get("frames") for k, v in d.get("cards", {}).items()})
print("tracks", {k: len(v.get("track", [])) for k, v in d.get("cards", {}).items()})
