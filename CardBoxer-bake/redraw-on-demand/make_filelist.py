"""生成按需重绘归档清单（相对路径 + 字节数 + sha256），并验证稳定性。

两次连续运行内容必须逐字一致；任何文件在两次之间被改动都会 MISMATCH。
清单本身与 __pycache__ 不参与。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "redraw-on-demand-file-list.txt"
SKIP_NAMES = {OUT.name, "__pycache__"}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    files = []
    for p in sorted(HERE.rglob("*")):
        if not p.is_file() or p.name in SKIP_NAMES:
            continue
        if any(part == "__pycache__" for part in p.relative_to(HERE).parts):
            continue
        files.append(p)
    lines = ["《牌拳》redraw-on-demand · 文件清单", "目录: %s" % HERE.name,
             "共 %d 个文件" % len(files), ""]
    total = 0
    for p in files:
        b = p.read_bytes()
        total += len(b)
        lines.append("%-58s %10d  %s" % (p.relative_to(HERE).as_posix(), len(b), sha(b)))
    lines += ["", "总字节: %d" % total]
    content = "\n".join(lines) + "\n"
    if OUT.is_file():
        old = OUT.read_text(encoding="utf-8")
        if old != content:
            print("FILELIST_MISMATCH old=%d new=%d" % (len(old), len(content)))
            return 1
        print("FILELIST_STABLE_OK files=%d bytes=%d" % (len(files), total))
        return 0
    OUT.write_text(content, encoding="utf-8")
    print("FILELIST_CREATED files=%d bytes=%d" % (len(files), total))
    print("再跑一次确认 FILELIST_STABLE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
