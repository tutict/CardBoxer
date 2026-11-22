"""Generate a stable sha256 manifest of motion-integration-p0/ (top level + logs/).

Run twice in-process and compare byte-for-byte; FILELIST_STABLE_OK means no
hidden self-modifying entry slipped into the archive.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "motion-integration-p0-file-list.txt"


def build() -> str:
    rows = []
    for p in sorted(HERE.rglob("*")):
        if not p.is_file() or p == OUT:
            continue
        rel = p.relative_to(HERE).as_posix()
        b = p.read_bytes()
        rows.append("%-52s %9d  %s" % (rel, len(b), hashlib.sha256(b).hexdigest()))
    head = [
        "《牌拳》回合制战斗动作 P0 接线 · 文件清单",
        "目录: CardBoxer-bake/motion-integration-p0/",
        "格式: 相对路径 / 字节数 / sha256",
        "共 %d 项" % len(rows),
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
