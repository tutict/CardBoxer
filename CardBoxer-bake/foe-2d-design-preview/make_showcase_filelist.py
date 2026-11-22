"""生成 对手怪2D设计展示-文件清单.txt：相对路径 / 字节数 / sha256。

清单自身排除；__pycache__ 与 .pyc 排除。数字全部现算，不写死。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "foe-2d-design-preview-file-list.txt"

rows: list[tuple[str, int, str]] = []
for p in sorted(HERE.rglob("*")):
    if not p.is_file() or "__pycache__" in p.parts or p.suffix == ".pyc":
        continue
    rel = p.relative_to(HERE).as_posix()
    if rel == OUT.name:
        continue
    b = p.read_bytes()
    rows.append((rel, len(b), hashlib.sha256(b).hexdigest()))

w = max(len(r[0]) for r in rows)
lines = [
    "《牌拳》对手怪 V1 · 2D 设计展示文件清单",
    "=" * 72,
    f"目录：{HERE.as_posix()}",
    f"文件数：{len(rows)}（不含清单自身 / __pycache__ / .pyc）",
    "",
    f"{'相对路径'.ljust(w)}  {'bytes'.rjust(10)}  sha256",
    "-" * (w + 10 + 2 + 64 + 2),
]
for rel, size, digest in rows:
    lines.append(f"{rel.ljust(w)}  {str(size).rjust(10)}  {digest}")
lines += ["", "复算： <venv>/python.exe make_showcase_filelist.py"]
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"SHOWCASE_FILELIST_OK files={len(rows)} bytes={OUT.stat().st_size}")
