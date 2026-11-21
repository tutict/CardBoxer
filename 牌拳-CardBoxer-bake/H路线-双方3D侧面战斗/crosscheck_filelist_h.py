"""独立复核 H 路线文件清单：重新遍历目录，逐条比对路径/字节/sha256。

刻意不 import make_filelist_h.py，避免「两边用同一个错函数一起错」。
用法：python crosscheck_filelist_h.py
"""
from __future__ import annotations

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIST = HERE / "文件清单.txt"
SKIP_NAMES = {"文件清单.txt", "new-files.diff"}
SKIP_DIRS = {"logs", ".godot", "__pycache__", "orig"}


def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    actual = {}
    for p in HERE.rglob("*"):
        if not p.is_file() or p.name in SKIP_NAMES:
            continue
        rel = p.relative_to(HERE)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        key = str(rel).replace("\\", "/")
        actual[key] = (p.stat().st_size, digest(p))

    declared = {}
    for ln in LIST.read_bytes().decode("utf-8").splitlines():
        if not ln or ln.startswith("#"):
            continue
        parts = ln.split("\t")
        if len(parts) != 3:
            print("BAD ROW", repr(ln))
            continue
        declared[parts[0]] = (int(parts[1]), parts[2])

    bad = [k for k, v in declared.items() if actual.get(k) != v]
    extra = sorted(set(actual) - set(declared))
    missing = sorted(set(declared) - set(actual))
    ok = not bad and not extra and not missing and len(declared) > 40
    print(f"ROWS={len(declared)} ACTUAL={len(actual)} "
          f"BAD={len(bad)} EXTRA={len(extra)} MISSING={len(missing)}")
    for k in bad[:10]:
        print("  MISMATCH", k)
    for k in extra[:10]:
        print("  EXTRA", k)
    for k in missing[:10]:
        print("  MISSING", k)
    print("CROSSCHECK_H_OK" if ok else "CROSSCHECK_H_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
