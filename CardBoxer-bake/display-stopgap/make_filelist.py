"""生成本轮证据区的文件清单（相对路径 / 字节数 / sha256）。"""
from __future__ import annotations

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "file-list.txt"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    rows = []
    for p in sorted(HERE.rglob("*")):
        if not p.is_file() or p.name == OUT.name or "__pycache__" in p.parts:
            continue
        rows.append((p.relative_to(HERE).as_posix(),
                     p.stat().st_size, sha256(p)))
    lines = [f"display-stopgap 证据区文件清单  entries={len(rows)}", ""]
    lines += [f"{size:>10}  {sha}  {rel}" for rel, size, sha in rows]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"FILELIST_ENTRIES={len(rows)} BYTES={OUT.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
