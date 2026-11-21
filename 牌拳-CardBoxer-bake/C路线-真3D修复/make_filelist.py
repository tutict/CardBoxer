"""生成 C 路线目录文件清单；连跑两次比对内容，确认清单可复算且稳定。"""
from __future__ import annotations

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "C路线-文件清单.txt"
EXCLUDE = {OUT.name, "make_filelist.py", "filelist_snapshot.txt"}


def build() -> tuple[str, int]:
    lines = []
    for p in sorted(HERE.rglob("*")):
        if not p.is_file() or p.name in EXCLUDE or "__pycache__" in p.parts:
            continue
        rel = p.relative_to(HERE).as_posix()
        b = p.read_bytes()
        lines.append(f"{rel:<52} {len(b):>9}  {hashlib.sha256(b).hexdigest()}")
    parts = [
        "《牌拳》C 路线（真 3D 连续壳 + 平滑权重）文件清单",
        "=" * 76,
        f"目录：{HERE.name}",
        f"文件数：{len(lines)}（不含清单自身与生成脚本）",
        "",
        *lines,
        "",
        "复算： <venv>/python.exe make_filelist.py",
    ]
    return "\n".join(parts) + "\n", len(lines)


def main() -> int:
    a, n = build()
    assert a.count("《牌拳》C 路线（真 3D 连续壳 + 平滑权重）文件清单") == 1
    assert f"文件数：{n}（" in a, "header count must equal actual file count"
    OUT.write_text(a, encoding="utf-8")
    b, n2 = build()
    OUT.write_text(b, encoding="utf-8")
    stable = a == b and n == n2 and OUT.read_text(encoding="utf-8") == b
    print(f"FILELIST_OK files={n} bytes={OUT.stat().st_size} "
          f"{'FILELIST_STABLE_OK' if stable else 'FILELIST_UNSTABLE'}")
    return 0 if stable else 1


if __name__ == "__main__":
    raise SystemExit(main())
