"""P1 落地前：逐文件 sha256 基线 + 待改文件二进制备份。

用法：python make_baseline.py
产出：orig/pre-p1/（4 个待改文件的逐字节副本）、data/baseline.json
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parent.parent / "CardBoxer"
ORIG = HERE / "orig" / "pre-p1"
OUT = HERE / "data" / "baseline.json"

TO_CHANGE = [
    "scripts/arena.gd",
    "scripts/fighter_3d_layer.gd",
    "data/motion_input.json",
    "data/motion_input_foe.json",
]
WATCH = TO_CHANGE + [
    "scripts/fighter.gd",
    "scripts/rig_driver.gd",
    "scripts/battle_motion_p0.gd",
    "scripts/battle_rhythm.gd",
    "scripts/card_motion.gd",
    "scripts/hud.gd",
    "data/card_motion.json",
    "project.godot",
    "assets/3d/player-rigged.glb",
    "assets/3d/foe-rigged.glb",
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else ""


def main() -> int:
    ORIG.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = {}
    for rel in WATCH:
        p = GAME / rel
        rows[rel] = {"exists": p.is_file(),
                     "size": p.stat().st_size if p.is_file() else 0,
                     "sha256": sha(p)}
    for rel in TO_CHANGE:
        src = GAME / rel
        dst = ORIG / Path(rel).name
        dst.write_bytes(src.read_bytes())

    checks = {
        "all_watched_present": all(r["exists"] for r in rows.values()),
        "all_sha_nonempty": all(len(r["sha256"]) == 64
                                for r in rows.values()),
        "backups_bytewise_equal": all(
            (ORIG / Path(rel).name).read_bytes() == (GAME / rel).read_bytes()
            for rel in TO_CHANGE),
        "backup_count": len(list(ORIG.iterdir())) == len(TO_CHANGE),
        "four_to_change": len(TO_CHANGE) == 4,
    }
    report = {"game": str(GAME), "to_change": TO_CHANGE,
              "files": rows, "checks": checks,
              "ok": all(checks.values())}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for rel in TO_CHANGE:
        print("WATCH", rel, rows[rel]["sha256"][:12], rows[rel]["size"])
    for k, v in checks.items():
        print("CHECK", k, v)
    print("BASELINE_OK" if report["ok"] else "BASELINE_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
