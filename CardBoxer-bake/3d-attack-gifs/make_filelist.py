"""生成可复算的文件清单；两次生成逐字节一致才算 STABLE_OK。

顶层逐文件给 sha256，frames/ 与 logs/ 只给数量+总字节+整体聚合指纹，
避免清单本身比帧目录还长。清单头部不写时间戳，保证可重复。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "3d-attack-gifs-file-list.txt"
SKIP = {OUT.name}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def build():
    lines = ["《牌拳》3D 攻击 GIF 交付 · 文件清单",
             "目录：CardBoxer-bake/3d-attack-gifs/",
             "口径：顶层逐文件 sha256；子目录给文件数/总字节/逐文件聚合指纹。",
             ""]
    top = sorted((p for p in HERE.iterdir() if p.is_file() and p.name not in SKIP),
                 key=lambda p: p.name)
    lines.append(f"顶层文件 {len(top)} 个")
    lines.append("-" * 78)
    total = 0
    for p in top:
        b = p.read_bytes()
        total += len(b)
        lines.append(f"{p.name:<46} {len(b):>10} B  {sha(b)}")
    lines.append("-" * 78)
    lines.append(f"顶层合计 {total} B")
    lines.append("")
    for d in sorted(p for p in HERE.iterdir() if p.is_dir()):
        files = sorted((q for q in d.rglob("*") if q.is_file()),
                       key=lambda q: str(q.relative_to(HERE)))
        size = sum(q.stat().st_size for q in files)
        agg = hashlib.sha256()
        for q in files:
            agg.update(str(q.relative_to(HERE)).replace("\\", "/").encode())
            agg.update(q.read_bytes())
        lines.append(f"{d.name}/  文件数={len(files)}  总字节={size} B")
        lines.append(f"  聚合 sha256 = {agg.hexdigest()}")
        for q in files:
            lines.append(f"    {str(q.relative_to(HERE)).replace(chr(92), '/')}"
                         f"  {q.stat().st_size} B")
    lines.append("")
    return "\n".join(lines) + "\n"


a = build()
OUT.write_text(a, encoding="utf-8")
b = build()
stable = a == b
print(f"FILELIST lines={a.count(chr(10))} "
      f"{'FILELIST_STABLE_OK' if stable else 'FILELIST_MISMATCH'}")
raise SystemExit(0 if stable else 1)
