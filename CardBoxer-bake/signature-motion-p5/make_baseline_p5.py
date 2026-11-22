# -*- coding: utf-8 -*-
"""P5 规格阶段源码基线：只记录 sha256，不改任何被监控文件。

清单沿用 P4 的 14 个受监控文件（含两个真实 GLB），保证两轮口径一致。
产出 orig/spec-baseline.json。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parent.parent / "CardBoxer"

WATCHED = [
    "scripts/arena.gd",
    "scripts/fighter_3d_layer.gd",
    "scripts/fighter.gd",
    "scripts/rig_driver.gd",
    "scripts/battle_motion_p0.gd",
    "scripts/battle_rhythm.gd",
    "scripts/card_motion.gd",
    "scripts/hud.gd",
    "data/card_motion.json",
    "data/motion_input.json",
    "data/motion_input_foe.json",
    "project.godot",
    "assets/3d/player-rigged.glb",
    "assets/3d/foe-rigged.glb",
]

OUT = HERE / "orig" / "spec-baseline.json"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    files = {}
    for rel in WATCHED:
        p = GAME / rel
        files[rel] = {
            "exists": p.is_file(),
            "size": p.stat().st_size if p.is_file() else 0,
            "sha256": sha(p) if p.is_file() else "",
        }
    out = {
        "game": str(GAME),
        "stage": "P5 规格阶段（#213）；此后 #216 才会改三份动作表",
        "to_change_later": [
            "data/card_motion.json",
            "data/motion_input.json",
            "data/motion_input_foe.json",
        ],
        "files": files,
        "checks": {
            "all_watched_exist": all(v["exists"] for v in files.values()),
            "count": len(files),
        },
    }
    out["ok"] = out["checks"]["all_watched_exist"]
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("BASELINE_P5_OK" if out["ok"] else "BASELINE_P5_FAILED",
          "files=%d" % len(files))
    for rel, meta in files.items():
        print(f"  {rel:34s} {meta['size']:10d}  {meta['sha256'][:12]}")
    print("WROTE", OUT)


if __name__ == "__main__":
    main()
