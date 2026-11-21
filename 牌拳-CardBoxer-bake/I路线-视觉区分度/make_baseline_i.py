"""I 路线 P0：备份「H 完成态」的可运行游戏工程，写逐文件 size+sha256 基线。

二进制复制；排除 .godot/ 与 __pycache__/。
用法：python make_baseline_i.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
ORIG = HERE / "orig" / "pre-visual"
BASELINE = HERE / "baseline_i.json"
EXCLUDE_DIRS = {".godot", "__pycache__"}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def game_files() -> list[Path]:
    out = []
    for p in sorted(GAME.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(GAME)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        out.append(p)
    return out


def main() -> int:
    files = game_files()
    rows = []
    for p in files:
        rel = p.relative_to(GAME)
        dst = ORIG / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
        rows.append({"rel": str(rel).replace("\\", "/"),
                     "size": p.stat().st_size,
                     "sha256": sha256(p)})
    mismatch = []
    for row in rows:
        q = ORIG / row["rel"]
        if not q.is_file() or q.stat().st_size != row["size"] \
                or sha256(q) != row["sha256"]:
            mismatch.append(row["rel"])
    payload = {
        "game": str(GAME), "count": len(rows),
        "backup": str(ORIG), "backup_verified": not mismatch,
        "backup_mismatch": mismatch, "files": rows,
    }
    BASELINE.write_text(json.dumps(payload, ensure_ascii=False, indent=2)
                        + "\n", encoding="utf-8")
    print(f"BASELINE_FILES={len(rows)} BACKUP_VERIFIED={not mismatch} "
          f"MISMATCH={len(mismatch)}")
    print("BASELINE_I_OK" if not mismatch else "BASELINE_I_FAILED")
    return 0 if not mismatch else 1


if __name__ == "__main__":
    raise SystemExit(main())
