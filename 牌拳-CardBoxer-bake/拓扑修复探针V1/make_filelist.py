"""生成目录文件清单（排除清单自身与快照，避免自己把自己算进去）。"""
from __future__ import annotations

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "拓扑修复探针-文件清单.txt"
EXCLUDE = {OUT.name, "filelist_snapshot.txt", "make_filelist.py"}

lines = []
for p in sorted(HERE.rglob("*")):
    if not p.is_file() or p.name in EXCLUDE:
        continue
    rel = p.relative_to(HERE).as_posix()
    b = p.read_bytes()
    lines.append(f"{rel:<48} {len(b):>9}  {hashlib.sha256(b).hexdigest()}")

parts = [
    "《牌拳》拓扑修复探针 文件清单",
    "=" * 64,
    f"目录：{HERE.name}",
    f"文件数：{len(lines)}（不含清单自身与生成脚本）",
    "",
    *lines,
    "",
    "复算： <venv>/python.exe make_filelist.py",
]
text = "\n".join(parts) + "\n"
# 「两次生成一致」不等于「内容正确」：首版漏了 + 号，把标题重复了 64 次，
# 而稳定性比对照样 STABLE_OK。这里显式钉住标题只出现一次。
assert text.count("《牌拳》拓扑修复探针 文件清单") == 1, "header duplicated"
assert text.count("\n" + "=" * 64 + "\n") == 1, "separator missing/duplicated"
OUT.write_text(text, encoding="utf-8")
print(f"FILELIST_OK files={len(lines)} bytes={OUT.stat().st_size} header_once=True")
