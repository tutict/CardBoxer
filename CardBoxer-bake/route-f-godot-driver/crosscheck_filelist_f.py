"""外部独立复核文件清单：不 import make_filelist_f.py，自己遍历+算 sha。

用法：python crosscheck_filelist_f.py
"""
from __future__ import annotations

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIST = HERE / "file-list.txt"
EXCLUDE_NAMES = {"file-list.txt", "new-files.diff"}
EXCLUDE_DIRS = {"logs", ".godot", "__pycache__"}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    rows = [l for l in LIST.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")]
    listed = {}
    for line in rows:
        rel, size, digest = line.split("\t")
        listed[rel] = (int(size), digest)
    actual = {}
    for p in HERE.rglob("*"):
        if not p.is_file() or p.name in EXCLUDE_NAMES:
            continue
        relp = p.relative_to(HERE)
        if any(x in EXCLUDE_DIRS for x in relp.parts):
            continue
        rel = str(relp).replace("\\", "/")
        actual[rel] = (p.stat().st_size, sha256(p))
    bad = sorted(k for k in listed
                 if k not in actual or actual[k] != listed[k])
    extra = sorted(set(actual) - set(listed))
    ok = not bad and not extra and len(rows) >= 20
    print(f"ROWS={len(rows)} ACTUAL={len(actual)} "
          f"BAD={len(bad)} EXTRA={len(extra)}")
    for k in bad[:10]:
        print("  BAD", k)
    for k in extra[:10]:
        print("  EXTRA", k)
    print("CROSSCHECK_OK" if ok else "CROSSCHECK_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
