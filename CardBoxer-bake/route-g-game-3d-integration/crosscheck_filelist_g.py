"""G 路线：不经 make_filelist_g.py 的代码，独立复核清单每一行。

目的：清单生成脚本自己写自己验，逻辑错了会自洽地假绿。这里从
文件系统重新枚举，按同一口径独立算 size/sha256，逐行比对。

用法：python crosscheck_filelist_g.py
"""
from __future__ import annotations

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIST = HERE / "file-list.txt"
EXCLUDE_NAMES = {"file-list.txt", "new-files.diff"}
EXCLUDE_DIRS = {"logs", ".godot", "__pycache__", "orig", "baseline_project"}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    assert LIST.is_file(), LIST
    rows = {}
    for line in LIST.read_bytes().decode("utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        rel, size, sha = line.split("\t")
        rows[rel] = (int(size), sha)
    actual = {}
    for p in HERE.rglob("*"):
        if not p.is_file() or p.name in EXCLUDE_NAMES:
            continue
        rel = p.relative_to(HERE)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        key = str(rel).replace("\\", "/")
        actual[key] = (p.stat().st_size, sha256(p))
    bad = [k for k, v in rows.items()
           if k not in actual or actual[k] != v]
    extra = sorted(set(actual) - set(rows))
    missing = sorted(set(rows) - set(actual))
    ok = not bad and not extra and not missing
    print(f"ROWS={len(rows)} ACTUAL={len(actual)} BAD={len(bad)} "
          f"EXTRA={len(extra)} MISSING={len(missing)}")
    for k in bad[:5]:
        print("  BAD", k)
    for k in extra[:5]:
        print("  EXTRA", k)
    print("CROSSCHECK_OK" if ok else "CROSSCHECK_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
