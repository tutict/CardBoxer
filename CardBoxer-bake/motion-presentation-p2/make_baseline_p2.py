"""P2 落地前：备份 2 个待改数据文件，并记录 14 个受监控文件的 sha256。

用法：python make_baseline_p2.py
产出：orig/pre-p2/*、data/baseline_p2.json
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "CardBoxer"
ORIG = HERE / "orig" / "pre-p2"
OUT = HERE / "data" / "baseline_p2.json"

TO_CHANGE = ["data/motion_input.json", "data/motion_input_foe.json"]
WATCHED = [
    "scripts/arena.gd",
    "scripts/fighter_3d_layer.gd",
    "data/motion_input.json",
    "data/motion_input_foe.json",
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


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ORIG.mkdir(parents=True, exist_ok=True)
    files = {}
    for rel in WATCHED:
        p = GAME / rel
        files[rel] = {"exists": p.is_file(),
                      "size": p.stat().st_size if p.is_file() else 0,
                      "sha256": sha256(p) if p.is_file() else ""}
    backups = {}
    for rel in TO_CHANGE:
        src = GAME / rel
        dst = ORIG / Path(rel).name
        dst.write_bytes(src.read_bytes())
        backups[rel] = {"backup": str(dst),
                        "bytewise_equal": sha256(dst) == files[rel]["sha256"]}
    checks = {
        "all_watched_present": all(v["exists"] for v in files.values()),
        "all_sha_nonempty": all(len(v["sha256"]) == 64
                                for v in files.values()),
        "backups_bytewise_equal": all(v["bytewise_equal"]
                                      for v in backups.values()),
        "fourteen_watched": len(files) == 14,
        "two_to_change": len(TO_CHANGE) == 2,
    }
    report = {"game": str(GAME), "to_change": TO_CHANGE,
              "files": files, "backups": backups,
              "checks": checks, "ok": all(checks.values())}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k, v in checks.items():
        print("CHECK", k, v)
    print("BASELINE_P2_OK" if report["ok"] else "BASELINE_P2_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
