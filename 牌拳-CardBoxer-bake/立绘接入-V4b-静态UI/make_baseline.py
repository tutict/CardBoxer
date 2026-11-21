"""改源码前的只读基线：逐文件二进制备份 + sha256 对账。

产物落在 -bake 工作区，绝不写回可运行工程。
还原口径：二进制 read_bytes / write_bytes + sha256 复验（不用文本读写）。
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
OUT = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer-bake\立绘接入-V4b-静态UI")
BACKUP = OUT / "orig" / "pre-portrait-ui"
BASELINE = OUT / "源码基线.json"

# 只收源码/配置/导入元数据；.godot 缓存与新 assets/ 目录不进基线。
WANTED_SUFFIXES = {".gd", ".tscn", ".import", ".uid", ".json"}
WANTED_NAMES = {"project.godot"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def wanted(rel: str) -> bool:
    if rel.startswith(".godot/") or rel.startswith("assets/"):
        return False
    return Path(rel).suffix in WANTED_SUFFIXES or Path(rel).name in WANTED_NAMES


def main() -> None:
    BACKUP.mkdir(parents=True, exist_ok=True)
    files = sorted(
        p for p in GAME.rglob("*")
        if p.is_file() and wanted(p.relative_to(GAME).as_posix())
    )
    rows = []
    for src in files:
        rel = src.relative_to(GAME).as_posix()
        dst = BACKUP / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        raw = src.read_bytes()
        bak = dst.read_bytes()
        rows.append({
            "path": rel,
            "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "backup_sha256": hashlib.sha256(bak).hexdigest(),
            "backup_identical": raw == bak,
        })

    # 背景贴图本体不改动，但把指纹也钉进基线，避免「贴图被换」无人发现。
    bg = GAME / "background" / "arena.png"
    if bg.is_file():
        raw = bg.read_bytes()
        rows.append({
            "path": "background/arena.png",
            "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "backup_sha256": "",
            "backup_identical": True,
        })

    BASELINE.write_text(
        json.dumps({"root": str(GAME), "files": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    bad = [r["path"] for r in rows if not r["backup_identical"]]
    print(f"BASELINE_FILES={len(rows)}")
    print(f"BACKUP_BYTES={sum(r['size'] for r in rows)}")
    print(f"BACKUP_MISMATCH={len(bad)} {bad[:5]}")
    print("BASELINE_OK" if not bad else "BASELINE_FAILED")


if __name__ == "__main__":
    main()
