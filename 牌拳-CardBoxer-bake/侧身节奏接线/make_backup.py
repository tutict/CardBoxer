"""Snapshot the CURRENT (post-P0-wiring) game tree before the rhythm layer.

Writes orig/pre-side-rhythm/ plus 备份指纹.json. Binary copy only; the
manifest is used by verify_rhythm.py to prove exactly which files changed.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
BAKE = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer-bake")
BACKUP = BAKE / "orig" / "pre-side-rhythm"
HERE = Path(__file__).resolve().parent

FILES = [
    "scripts/arena.gd",
    "scripts/hud.gd",
    "scripts/fighter.gd",
    "scripts/fx_layer.gd",
    "scripts/fighter_skin.gd",
    "scripts/card_data.gd",
    "scripts/card_motion.gd",
    "scripts/taikou_rules.gd",
    "scripts/taikou_rage.gd",
    "scripts/taikou_ai.gd",
    "scripts/battle_motion_p0.gd",
    "scripts/combo_check.gd",
    "tests/battle_motion_p0_check.gd",
    "tests/taikou_flow_check.gd",
    "project.godot",
]


def main() -> int:
    BACKUP.mkdir(parents=True, exist_ok=True)
    rows = {}
    for rel in FILES:
        src = GAME / rel
        if not src.is_file():
            print("MISSING: %s" % rel)
            return 2
        dst = BACKUP / Path(rel).name
        shutil.copy2(src, dst)
        b = dst.read_bytes()
        rows[rel] = {"backup_file": dst.name,
                     "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)}
    (HERE / "备份指纹.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("BACKUP_OK files=%d" % len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
