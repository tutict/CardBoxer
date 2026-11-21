"""生成 B 路线 P0 证据区文件清单（相对路径 + 字节数 + sha256）。

用法：python make_filelist.py
"""
from __future__ import annotations

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "文件清单.txt"
SKIP_DIRS = {"__pycache__", ".pytest_cache"}


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    rows = []
    for p in sorted(HERE.rglob("*")):
        if not p.is_file() or p.name == OUT.name:
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(HERE).parts[:-1]):
            continue
        rows.append((str(p.relative_to(HERE)).replace("\\", "/"),
                     p.stat().st_size, sha(p)))
    lines = [
        "《牌拳》B 路线 P0 · 资产层叠层诊断 · 文件清单",
        "日期：2026-11-14",
        f"文件数：{len(rows)}",
        f"总字节：{sum(r[1] for r in rows):,}",
        "-" * 92,
    ]
    for path, size, digest in rows:
        lines.append(f"{size:>10}  {digest[:16]}  {path}")
    lines += ["-" * 92,
              "说明：只读取证；游戏工程仅 tests/ 下新增 4 个探针脚本，",
              "      scripts/ 玩法源码、GLB、贴图、project.godot 全部零改动。"]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("FILES", len(rows), "BYTES", sum(r[1] for r in rows))
    print("FILELIST_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
