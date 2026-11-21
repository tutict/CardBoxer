"""外部逐行复算 D 路线文件清单：size + sha256 + 反向漏项。

与生成器 make_filelist_d.py 完全独立，不 import 生成器、不复用其枚举。
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

WORK = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer-bake\D路线-CreativeReview与引擎截帧")
LIST = WORK / "文件清单.txt"
EXCLUDED = {"文件清单.txt", "new-files-d.diff", "logs/make_filelist_d.log"}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


rows: list[tuple[str, int, str]] = []
for line in LIST.read_text(encoding="utf-8").splitlines():
    if not line.startswith("WORK/"):
        continue
    parts = line.split()
    rows.append((parts[0][len("WORK/"):], int(parts[1]), parts[2]))

bad: list[tuple[str, str]] = []
for rel, size, digest in rows:
    p = WORK / rel
    if not p.is_file():
        bad.append((rel, "MISSING"))
        continue
    real_size = p.stat().st_size
    if real_size != size:
        bad.append((rel, f"SIZE listed={size} real={real_size}"))
    if sha256(p) != digest:
        bad.append((rel, "SHA256"))

listed = {r[0] for r in rows}
extra: list[str] = []
for p in sorted(WORK.rglob("*")):
    if not p.is_file():
        continue
    rel = p.relative_to(WORK).as_posix()
    if rel in EXCLUDED:
        continue
    if rel.startswith("probe_project_d/.godot/") or rel.endswith(".tmp"):
        continue
    if rel not in listed:
        extra.append(rel)

print(f"ROWS={len(rows)} BAD={len(bad)} EXTRA={len(extra)}")
for item in bad[:20]:
    print("BAD", item)
for item in extra[:20]:
    print("EXTRA", item)
ok = not bad and not extra
print("CROSSCHECK_OK" if ok else "CROSSCHECK_FAILED")
sys.exit(0 if ok else 1)
