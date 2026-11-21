"""World3D 接线修复 · 改动前基线快照（只读工程 + 写本区 data/）。

用途：落地 setup() 改动后，逐文件对账 sha256，证明「只有一行源码变了」，
GLB / 贴图 / 其余玩法源码 / project.godot 一个字节没动。

用法：python make_baseline.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
OUT = HERE / "data" / "baseline.json"
BACKUP = HERE / "orig" / "pre-world3d" / "fighter_3d_layer.gd"

WATCH = [
    "scripts/fighter_3d_layer.gd",
    "scripts/arena.gd",
    "scripts/fighter.gd",
    "scripts/hud.gd",
    "scripts/rig_driver.gd",
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
    rows = {}
    for rel in WATCH:
        p = GAME / rel
        rows[rel] = {
            "exists": p.is_file(),
            "size": p.stat().st_size if p.is_file() else 0,
            "sha256": sha256(p) if p.is_file() else "",
            "mtime": int(p.stat().st_mtime) if p.is_file() else 0,
        }
    # assets/3d 下所有贴图与 .import 也钉住（不猜文件名）
    for p in sorted((GAME / "assets" / "3d").rglob("*")):
        if not p.is_file() or p.suffix.lower() == ".glb":
            continue
        rel = p.relative_to(GAME).as_posix()
        rows[rel] = {"exists": True, "size": p.stat().st_size,
                     "sha256": sha256(p), "mtime": int(p.stat().st_mtime)}

    src = rows["scripts/fighter_3d_layer.gd"]["sha256"]
    bak = sha256(BACKUP) if BACKUP.is_file() else ""
    checks = {
        "all_watch_files_exist": all(r["exists"] for r in rows.values()),
        "backup_exists": BACKUP.is_file(),
        "backup_matches_source": bool(bak) and bak == src,
        "two_glbs_present": all(rows[r]["exists"] for r in WATCH
                                if r.endswith(".glb")),
        "asset_count_sane": len(rows) >= 10,
    }
    report = {
        "files": rows,
        "file_count": len(rows),
        "pre_source_sha256": src,
        "backup_sha256": bak,
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k, v in checks.items():
        print("CHECK", k, v)
    print("BASELINE_OK" if report["ok"] else "BASELINE_FAILED",
          "files=", len(rows), "src_sha=", src[:12])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
