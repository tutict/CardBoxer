"""Generate a stable sha256 manifest of 侧身节奏接线/ (top level + logs/).

Run twice in-process and compare byte-for-byte; FILELIST_STABLE_OK means no
hidden self-modifying entry slipped into the archive. __pycache__ / *.pyc are
excluded on purpose: they are interpreter artifacts, not deliverables.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "侧身节奏接线-文件清单.txt"


def build() -> str:
    rows = []
    for p in sorted(HERE.rglob("*")):
        if not p.is_file() or p == OUT:
            continue
        rel = p.relative_to(HERE).as_posix()
        if "__pycache__" in rel or rel.endswith(".pyc"):
            continue
        b = p.read_bytes()
        rows.append("%-52s %9d  %s" % (rel, len(b), hashlib.sha256(b).hexdigest()))
    head = [
        "《牌拳》B 路线 侧身节奏接线 · 文件清单",
        "目录: 牌拳-CardBoxer-bake/侧身节奏接线/",
        "格式: 相对路径 / 字节数 / sha256",
        "共 %d 项（不含 __pycache__ / *.pyc）" % len(rows),
        "-" * 100,
    ]
    return "\n".join(head + rows) + "\n"


def main() -> int:
    a = build()
    OUT.write_text(a, encoding="utf-8")
    b = build()
    ok = a == b
    print("entries=%d stable=%s" % (len(a.splitlines()) - 5, ok))
    print("FILELIST_STABLE_OK" if ok else "FILELIST_UNSTABLE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
