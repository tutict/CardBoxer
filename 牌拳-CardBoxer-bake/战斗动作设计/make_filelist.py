"""生成目录文件清单（排除清单自身与生成脚本，避免把自己算进去）。"""
from __future__ import annotations

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "战斗动作设计-文件清单.txt"
EXCLUDE = {OUT.name, "make_filelist.py", "filelist_snapshot.txt"}

lines = []
for p in sorted(HERE.rglob("*")):
    if not p.is_file() or p.name in EXCLUDE or "__pycache__" in p.parts:
        continue
    rel = p.relative_to(HERE).as_posix()
    b = p.read_bytes()
    lines.append(f"{rel:<44} {len(b):>9}  {hashlib.sha256(b).hexdigest()}")

parts = [
    "《牌拳》战斗动作设计 文件清单",
    "=" * 64,
    f"目录：{HERE.name}",
    f"文件数：{len(lines)}（不含清单自身与生成脚本）",
    "",
    *lines,
    "",
    "复算： <venv>/python.exe make_filelist.py",
]
text = "\n".join(parts) + "\n"
assert text.count("《牌拳》战斗动作设计 文件清单") == 1, "header duplicated"
OUT.write_text(text, encoding="utf-8")
print(f"FILELIST_OK files={len(lines)} bytes={OUT.stat().st_size} header_once=True")
