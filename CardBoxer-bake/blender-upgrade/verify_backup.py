"""Byte-for-byte verification of the Blender 4.4 leftover backup.

Run after copying the tree, and again after any cleanup, to prove the backup is
complete and unchanged. Exits 0 only when every relative path and every sha256
match, and prints explicit counts (no silent partial success).
"""

from __future__ import annotations

import hashlib
import os
import sys

SRC = r"C:\Program Files\Blender Foundation\Blender 4.4"
DST = r"D:\Projects\CardBoxer\CardBoxer-bake\blender-upgrade\backup-Blender4.4"


def index(root: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace("\\", "/")
            digest = hashlib.sha256()
            with open(path, "rb") as handle:
                while True:
                    block = handle.read(1 << 20)
                    if not block:
                        break
                    digest.update(block)
            out[rel] = digest.hexdigest()
    return out


def main() -> int:
    if not os.path.isdir(DST):
        print(f"FATAL backup missing: {DST}")
        return 2
    src = index(SRC)
    dst = index(DST)
    missing = sorted(set(src) - set(dst))
    extra = sorted(set(dst) - set(src))
    changed = sorted(k for k in set(src) & set(dst) if src[k] != dst[k])
    total_src = sum(os.path.getsize(os.path.join(SRC, k.replace("/", os.sep))) for k in src)
    total_dst = sum(os.path.getsize(os.path.join(DST, k.replace("/", os.sep))) for k in dst)
    print(f"source files={len(src)} bytes={total_src}")
    print(f"backup files={len(dst)} bytes={total_dst}")
    print(f"missing={len(missing)} extra={len(extra)} changed={len(changed)}")
    for label, items in (("MISSING", missing), ("EXTRA", extra), ("CHANGED", changed)):
        for item in items[:10]:
            print(f"  {label} {item}")
    ok = not missing and not extra and not changed and len(src) == 209 and total_src == total_dst
    print("BACKUP_OK" if ok else "BACKUP_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
