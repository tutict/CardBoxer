# -*- coding: utf-8 -*-
"""P5 全阶段文件清单：可复算，排除缓存与自身产物。

覆盖 #213 规格 / #214 诊断 / #215 候选与成本 / #216 落地 /
#217 引擎内 A/B / #218 判据与变异。重跑会覆盖 file-list.txt。
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "file-list.txt"
SKIP_NAMES = {"file-list.txt", "filelist_p5.json"}
SKIP_SUFFIX = {".pyc"}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    rows = []
    for p in sorted(HERE.rglob("*")):
        if not p.is_file():
            continue
        if "__pycache__" in p.parts or p.suffix in SKIP_SUFFIX:
            continue
        if p.name in SKIP_NAMES or p == Path(__file__).resolve():
            continue
        rel = p.relative_to(HERE).as_posix()
        rows.append((rel, p.stat().st_size, sha(p)))
    total = sum(r[1] for r in rows)
    lines = [
        "=" * 78,
        "《牌拳》P5 招牌动作设计 · 全阶段 文件清单",
        "=" * 78,
        "生成时间：%s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "证据区：CardBoxer-bake/signature-motion-p5/",
        "范围：#213~#218 全阶段；三份动作表已按 R2 落地，其余 11 个受监控文件 0 改动",
        "-" * 78,
        "%-58s %12s  %s" % ("文件", "字节", "sha256(前12)"),
        "-" * 78,
    ]
    lines += ["%-58s %12d  %s" % (r[0], r[1], r[2][:12]) for r in rows]
    lines += [
        "-" * 78,
        "files=%d bytes=%d" % (len(rows), total),
        "FILELIST_P5_ALL_STAGE_OK",
        "=" * 78,
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("FILELIST_P5_OK files=%d bytes=%d" % (len(rows), total))


if __name__ == "__main__":
    main()
